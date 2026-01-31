"""
IntelligentViolationDetector — система многофакторного анализа для детектирования нарушений.

Анализирует подключения пользователей на основе:
- Временных паттернов
- Геолокации
- Типа провайдера (ASN)
- Исторического профиля пользователя
- Fingerprint устройств
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from enum import Enum

from src.services.database import DatabaseService
from src.services.connection_monitor import ConnectionMonitor, ActiveConnection, ConnectionStats
from src.services.geoip import GeoIPService, IPMetadata, get_geoip_service
from src.utils.logger import logger


class ViolationAction(Enum):
    """Рекомендуемое действие при нарушении."""
    NO_ACTION = "no_action"
    MONITOR = "monitor"
    WARN = "warn"
    SOFT_BLOCK = "soft_block"
    TEMP_BLOCK = "temp_block"
    HARD_BLOCK = "hard_block"


@dataclass
class TemporalScore:
    """Скор временного анализа."""
    score: float
    reasons: List[str]
    simultaneous_connections_count: int = 0
    rapid_switches_count: int = 0


@dataclass
class GeoScore:
    """Скор географического анализа."""
    score: float
    reasons: List[str]
    countries: Set[str]
    cities: Set[str]
    impossible_travel_detected: bool = False


@dataclass
class ASNScore:
    """Скор анализа провайдера."""
    score: float
    reasons: List[str]
    asn_types: Set[str]
    is_mobile_carrier: bool = False
    is_datacenter: bool = False
    is_vpn: bool = False


@dataclass
class ProfileScore:
    """Скор анализа профиля пользователя."""
    score: float
    reasons: List[str]
    deviation_from_baseline: float = 0.0


@dataclass
class DeviceScore:
    """Скор анализа устройств."""
    score: float
    reasons: List[str]
    unique_fingerprints_count: int = 0
    different_os_count: int = 0
    os_list: List[str] = None  # Список конкретных ОС (Android, iOS, Windows...)
    client_list: List[str] = None  # Список конкретных клиентов (V2RayNG, Shadowrocket...)


@dataclass
class ViolationScore:
    """Итоговый скор нарушения."""
    total: float
    breakdown: Dict[str, Any]
    recommended_action: ViolationAction
    confidence: float
    reasons: List[str]


class TemporalAnalyzer:
    """
    Анализ временных паттернов смены IP.
    
    Правила:
    - Последовательная смена IP (gap > 5 мин) = 0 (нормально)
    - Быстрая смена IP (gap < 1 мин), близкие гео = +10
    - Быстрая смена IP, далёкие гео = +40
    - Одновременные соединения = +80
    - Одновременные соединения > 3 IP = +100
    """
    
    def analyze(
        self,
        connections: List[ActiveConnection],
        connection_history: List[Dict[str, Any]],
        user_device_count: int = 1
    ) -> TemporalScore:
        """
        Анализирует временные паттерны подключений.
        
        Args:
            connections: Активные подключения
            connection_history: История подключений за период
            user_device_count: Количество устройств пользователя (для учёта нормальных одновременных подключений)
        
        Returns:
            TemporalScore с оценкой и причинами
        """
        score = 0.0
        reasons = []
        rapid_switches = 0
        
        # Проверка одновременных подключений
        # Считаем уникальные IP и проверяем, действительно ли подключения одновременные
        # Подключения считаются одновременными только если они созданы в пределах окна
        # (2 минуты) - это учитывает нормальное переключение между сетями (Wi-Fi <-> мобильная)
        # Также учитываем роутинг в приложении - пользователь может периодически подключаться/отключаться
        if len(connections) > 1:
            simultaneous_window_seconds = 120  # Окно для определения одновременности (2 минуты)
            reconnect_threshold_seconds = 300  # Порог для определения переподключения (5 минут)
            # Если между подключениями больше 5 минут, это переподключение через роутинг, а не одновременное подключение
            max_connection_age_hours = 24  # Максимальный возраст подключения для учёта
            # Учитываем количество устройств пользователя - если у пользователя несколько устройств,
            # то несколько одновременных подключений могут быть нормальными
            max_allowed_simultaneous = max(1, user_device_count)
            
            # Собираем все валидные времена подключений
            valid_connections = []
            now = datetime.utcnow()
            
            for conn in connections:
                conn_time = conn.connected_at
                if isinstance(conn_time, str):
                    try:
                        conn_time = datetime.fromisoformat(conn_time.replace('Z', '+00:00'))
                    except ValueError:
                        continue
                
                if not isinstance(conn_time, datetime):
                    continue
                
                # Убираем timezone для сравнения
                if conn_time.tzinfo:
                    conn_time = conn_time.replace(tzinfo=None)
                
                # Пропускаем слишком старые подключения (старше 24 часов)
                age_hours = (now - conn_time).total_seconds() / 3600
                if age_hours > max_connection_age_hours:
                    continue
                
                # Пропускаем подключения, которые были неактивны слишком долго (более 5 минут)
                # Это переподключения через роутинг, а не одновременные подключения
                age_seconds = (now - conn_time).total_seconds()
                if age_seconds > reconnect_threshold_seconds:
                    # Если подключение старше 5 минут и нет других активных подключений,
                    # это может быть переподключение, но мы всё равно учитываем его для анализа
                    # (но не как одновременное подключение)
                    pass
                
                valid_connections.append((conn_time, str(conn.ip_address)))
            
            # Если есть валидные подключения, проверяем одновременность
            if len(valid_connections) > 1:
                # Сортируем по времени подключения
                valid_connections.sort(key=lambda x: x[0])
                
                # Группируем подключения по временным окнам
                # Подключения считаются одновременными только если они созданы в пределах окна (2 минуты) друг от друга
                # И между ними нет большого разрыва (что указывало бы на последовательное переключение)
                simultaneous_groups = []
                current_group = [valid_connections[0]]
                
                for conn_time, ip in valid_connections[1:]:
                    # Проверяем разрыв между текущим и предыдущим подключением
                    prev_conn_time = current_group[-1][0]
                    time_diff_seconds = (conn_time - prev_conn_time).total_seconds()
                    
                    # Если разрыв больше порога переподключения (5 минут), это переподключение через роутинг
                    # Не считаем это одновременным подключением
                    if time_diff_seconds > reconnect_threshold_seconds:
                        # Начинаем новую группу (это переподключение, а не одновременное подключение)
                        if len(current_group) > 1:
                            simultaneous_groups.append(current_group)
                        current_group = [(conn_time, ip)]
                        continue
                    
                    # Проверяем, попадает ли подключение в текущую группу
                    # (в пределах окна от самого раннего подключения в группе)
                    earliest_in_group = current_group[0][0]
                    time_diff_from_earliest_seconds = (conn_time - earliest_in_group).total_seconds()
                    
                    # Подключение считается одновременным только если:
                    # 1. Оно в пределах окна от самого раннего подключения в группе
                    # 2. Разрыв между подключениями не слишком большой (не более окна одновременности)
                    # 3. Разрыв не превышает порог переподключения (уже проверено выше)
                    # 4. Разрыв больше 0.1 сек (если 0.0 сек, это разные события в одной секунде из-за округления)
                    if (time_diff_from_earliest_seconds <= simultaneous_window_seconds and 
                        time_diff_seconds <= simultaneous_window_seconds and
                        time_diff_seconds >= 0.1):  # Игнорируем разницу 0.0 сек (округление времени)
                        current_group.append((conn_time, ip))
                    else:
                        # Начинаем новую группу (есть разрыв, указывающий на последовательное переключение)
                        if len(current_group) > 1:
                            simultaneous_groups.append(current_group)
                        current_group = [(conn_time, ip)]
                
                # Добавляем последнюю группу
                if len(current_group) > 1:
                    simultaneous_groups.append(current_group)
                
                # Находим группу с максимальным количеством уникальных IP
                max_simultaneous_ips = 0
                for group in simultaneous_groups:
                    unique_ips = len(set(ip for _, ip in group))
                    max_simultaneous_ips = max(max_simultaneous_ips, unique_ips)
                
                # Если есть действительно одновременные подключения с разных IP
                if max_simultaneous_ips > 1:
                    simultaneous_count = max_simultaneous_ips

                    # Логика определения нарушения:
                    # - Базовый лимит = количество устройств пользователя
                    # - Буфер +1 на случай кратковременного overlap при переключении сети
                    # - Если IP > лимит + буфер - это превышение
                    #
                    # Примеры:
                    # - 1 устройство: лимит=1, буфер=1, порог=2 → 3+ IP = нарушение, 2 IP = предупреждение
                    # - 3 устройства: лимит=3, буфер=1, порог=4 → 5+ IP = нарушение, 4 IP = предупреждение
                    network_switch_buffer = 1
                    soft_threshold = max_allowed_simultaneous + network_switch_buffer  # Мягкий порог (предупреждение)
                    hard_threshold = max_allowed_simultaneous + network_switch_buffer + 1  # Жёсткий порог (нарушение)

                    # Сначала проверяем: IP > количества устройств?
                    # Это уже подозрительно, даже если в пределах буфера
                    if simultaneous_count > max_allowed_simultaneous:
                        excess_over_devices = simultaneous_count - max_allowed_simultaneous

                        if simultaneous_count > hard_threshold:
                            # Значительное превышение - точно нарушение
                            excess = simultaneous_count - hard_threshold
                            if excess >= 2 or simultaneous_count > 5:
                                # Сильное превышение
                                score = 100.0
                                reasons.append(f"Превышение лимита устройств: {simultaneous_count} IP при лимите {user_device_count} устройств (превышение на {excess_over_devices})")
                            else:
                                # Умеренное превышение
                                score = 80.0
                                reasons.append(f"Превышение лимита устройств: {simultaneous_count} IP при лимите {user_device_count} устройств")
                        elif simultaneous_count > soft_threshold:
                            # Небольшое превышение мягкого порога
                            score = 60.0
                            reasons.append(f"Возможное превышение лимита: {simultaneous_count} IP при лимите {user_device_count} устройств")
                        else:
                            # IP > устройств, но в пределах буфера - может быть переключение сети
                            # Даём небольшой скор для мониторинга
                            score = 40.0
                            reasons.append(f"Подозрительная активность: {simultaneous_count} IP при лимите {user_device_count} устройств (возможно переключение сети)")
                    # Если IP <= устройств - всё нормально, не добавляем скор
                    # Учитываем количество устройств пользователя с буфером для переключения сетей
                    # Буфер учитывает:
                    # - Переключение WiFi <-> Mobile (кратковременно 2 IP от одного устройства)
                    # - Роутинг с несколькими точками выхода
                    # - Погрешности определения времени отключения
                    #
                    # ВАЖНО: Буфер должен быть меньше для маленьких лимитов,
                    # иначе пользователь с лимитом 1 устройство может использовать 3 IP без детекции!
                    if user_device_count <= 1:
                        network_switch_buffer = 1  # Маленький буфер для лимита 1 устройство
                    elif user_device_count == 2:
                        network_switch_buffer = 1  # Маленький буфер для лимита 2 устройства
                    else:
                        network_switch_buffer = 2  # Стандартный буфер для 3+ устройств

                    effective_threshold = max_allowed_simultaneous + network_switch_buffer

                    # Если пользователь имеет много устройств (3+), даём дополнительный буфер
                    # т.к. несколько устройств могут одновременно переключать сети
                    if user_device_count >= 3:
                        effective_threshold += 1

                    # ПЕРВАЯ ПРОВЕРКА: Базовое превышение лимита устройств
                    # Если количество одновременных IP > лимита устройств, это уже подозрительно
                    # (даже если с буфером всё ещё ок)
                    if simultaneous_count > max_allowed_simultaneous:
                        excess_over_limit = simultaneous_count - max_allowed_simultaneous
                        if excess_over_limit >= 2:
                            # Превышение лимита на 2+ - это почти наверняка шаринг
                            score = max(score, 70.0)
                            reasons.append(f"Превышение лимита устройств: {simultaneous_count} IP одновременно при лимите {max_allowed_simultaneous} устройств (превышение на {excess_over_limit})")
                        else:
                            # Превышение на 1 - может быть переключение сетей, но заслуживает мониторинга
                            score = max(score, 55.0)
                            reasons.append(f"Возможное превышение лимита: {simultaneous_count} IP при лимите {max_allowed_simultaneous} устройств")

                    # ВТОРАЯ ПРОВЕРКА: Превышение с учётом буфера (более серьёзное нарушение)
                    if simultaneous_count > effective_threshold:
                        # Значительное превышение - вероятно шаринг
                        excess = simultaneous_count - effective_threshold
                        if excess >= 3 or simultaneous_count > 5:
                            # Сильное превышение - высокий скор
                            score = 100.0
                            reasons.append(f"Множественные одновременные подключения с {simultaneous_count} разных IP (превышение на {excess}, порог: {effective_threshold}, устройств: {user_device_count})")
                        elif excess >= 2:
                            # Умеренное превышение
                            score = max(score, 85.0)
                            reasons.append(f"Одновременные подключения с {simultaneous_count} разных IP (превышение на {excess}, порог: {effective_threshold}, устройств: {user_device_count})")
                        else:
                            # Минимальное превышение на 1 - добавляем к скору
                            score = max(score, 65.0)
                            reasons.append(f"Избыточные подключения: {simultaneous_count} IP (порог: {effective_threshold}, устройств: {user_device_count})")
                else:
                    # Если нет одновременных подключений, используем количество уникальных IP для статистики
                    simultaneous_count = len(set(ip for _, ip in valid_connections))
            elif len(valid_connections) == 1:
                # Одно валидное подключение
                simultaneous_count = 1
            else:
                # Нет валидных подключений (все старше 24 часов) - не считаем как одновременные
                simultaneous_count = 0
        elif len(connections) == 1:
            simultaneous_count = 1
        else:
            simultaneous_count = 0
        
        # Анализ быстрой смены IP в истории
        # Быстрое переключение между IP само по себе не является нарушением,
        # если старое подключение было отключено перед новым (нормальное переключение сетей)
        if len(connection_history) > 1:
            # Сортируем по времени подключения
            sorted_history = sorted(
                connection_history,
                key=lambda x: x.get("connected_at") or datetime.min
            )
            
            for i in range(1, len(sorted_history)):
                prev_conn = sorted_history[i - 1]
                curr_conn = sorted_history[i]
                
                prev_time = prev_conn.get("connected_at")
                curr_time = curr_conn.get("connected_at")
                prev_disconnected = prev_conn.get("disconnected_at")
                
                if not prev_time or not curr_time:
                    continue
                
                # Преобразуем в datetime если нужно
                if isinstance(prev_time, str):
                    try:
                        prev_time = datetime.fromisoformat(prev_time.replace('Z', '+00:00'))
                    except ValueError:
                        continue
                if isinstance(curr_time, str):
                    try:
                        curr_time = datetime.fromisoformat(curr_time.replace('Z', '+00:00'))
                    except ValueError:
                        continue
                if prev_disconnected and isinstance(prev_disconnected, str):
                    try:
                        prev_disconnected = datetime.fromisoformat(prev_disconnected.replace('Z', '+00:00'))
                    except ValueError:
                        prev_disconnected = None
                
                if not isinstance(prev_time, datetime) or not isinstance(curr_time, datetime):
                    continue
                
                # Убираем timezone для сравнения
                if prev_time.tzinfo:
                    prev_time = prev_time.replace(tzinfo=None)
                if curr_time.tzinfo:
                    curr_time = curr_time.replace(tzinfo=None)
                if prev_disconnected and isinstance(prev_disconnected, datetime):
                    if prev_disconnected.tzinfo:
                        prev_disconnected = prev_disconnected.replace(tzinfo=None)
                
                time_diff_seconds = (curr_time - prev_time).total_seconds()
                time_diff_minutes = time_diff_seconds / 60
                
                prev_ip = str(prev_conn.get("ip_address", ""))
                curr_ip = str(curr_conn.get("ip_address", ""))
                
                # Если IP разные и переключение быстрое (< 30 секунд)
                # НО: если разница 0.0 сек, это не переключение, а разные события в одной секунде
                # (из-за округления времени до секунды в логах)
                if prev_ip != curr_ip and 0.1 <= time_diff_seconds < 30:
                    # Проверяем, было ли старое подключение отключено перед новым
                    # Если да, это нормальное переключение сетей, не нарушение
                    is_normal_switch = False
                    if prev_disconnected and isinstance(prev_disconnected, datetime):
                        # Если старое подключение отключилось до или в момент нового подключения
                        if prev_disconnected <= curr_time:
                            is_normal_switch = True
                    
                    # Если старое подключение не отключено, но прошло достаточно времени (> 5 минут),
                    # считаем его устаревшим (зависшим), а не одновременным
                    now = datetime.utcnow()
                    if curr_time.tzinfo:
                        curr_time_with_tz = curr_time.replace(tzinfo=now.tzinfo if now.tzinfo else None)
                    else:
                        curr_time_with_tz = curr_time
                    time_since_switch = (now - curr_time_with_tz).total_seconds() / 60
                    
                    # Если переключение было более 5 минут назад, старое подключение могло "зависнуть"
                    # и не быть отключено, но это не означает одновременное подключение
                    is_old_switch = time_since_switch > 5
                    
                    # Проверяем, есть ли активные подключения со старым IP в текущий момент
                    old_ip_still_active_now = False
                    for conn in connections:
                        if str(conn.ip_address) == prev_ip:
                            conn_time = conn.connected_at
                            if isinstance(conn_time, str):
                                try:
                                    conn_time = datetime.fromisoformat(conn_time.replace('Z', '+00:00'))
                                except ValueError:
                                    continue
                            if isinstance(conn_time, datetime):
                                if conn_time.tzinfo:
                                    conn_time = conn_time.replace(tzinfo=None)
                                # Проверяем, что подключение не слишком старое (в пределах 5 минут)
                                conn_age_minutes = (now - conn_time).total_seconds() / 60
                                if conn_age_minutes <= 5:
                                    old_ip_still_active_now = True
                                    break
                    
                    # Быстрое переключение считается нарушением только если:
                    # 1. Старое подключение не было отключено (или отключилось после нового)
                    # 2. И есть активные подключения со старым IP СЕЙЧАС (не устаревшие)
                    # 3. И переключение очень быстрое (< 10 секунд) И происходит много раз
                    # 4. И это не старое переключение (произошло недавно)
                    # 5. И есть действительно одновременные подключения (simultaneous_count > 1)
                    if not is_normal_switch and old_ip_still_active_now and not is_old_switch:
                        rapid_switches += 1
                        # Добавляем скор только если есть признаки одновременных подключений
                        # Быстрое переключение само по себе не является нарушением
                        if simultaneous_count > 1:
                            # Добавляем скор только при множественных быстрых переключениях (3+)
                            # Одиночные переключения не добавляем - это дублирует инфо об одновременных подключениях
                            if rapid_switches >= 3:
                                score += 10.0
                                reasons.append(f"Множественные быстрые переключения между IP ({rapid_switches} раз)")
                    # Если это нормальное переключение (старое отключено) или старое переключение, не считаем нарушением
                    # Если нет одновременных подключений, быстрое переключение не считается нарушением
        
        return TemporalScore(
            score=min(score, 100.0),  # Максимум 100
            reasons=reasons,
            simultaneous_connections_count=simultaneous_count,
            rapid_switches_count=rapid_switches
        )


class GeoAnalyzer:
    """
    Анализ географического распределения IP.

    Правила:
    - Все IP из одного города = 0
    - IP из одной агломерации (пригороды) = 0 (нормально)
    - IP из разных городов одной страны (далеко) = +5
    - IP из разных стран, последовательно, реалистично = +15
    - IP из разных стран, нереалистичное время = +50
    - IP из разных стран одновременно = +90
    """

    # Скорости перемещения (км/ч)
    TRAVEL_SPEEDS = {
        'same_city': 50,      # км/ч (такси/метро)
        'same_country': 200,  # км/ч (поезд/машина)
        'international': 800, # км/ч (самолёт)
    }

    # Агломерации и пригороды - города, которые считаются одной локацией
    # Ключ - название агломерации, значение - список городов (включая центр)
    METROPOLITAN_AREAS = {
        # Свердловская область
        'yekaterinburg': [
            'yekaterinburg', 'ekaterinburg', 'sredneuralsk', 'verkhnyaya pyshma',
            'aramil', 'berezovsky', 'pervouralsk', 'revda', 'polevskoy',
            'sredneuralsk', 'verkhniaya pyshma', 'koltsovo', 'sysert'
        ],
        # Московская область
        'moscow': [
            'moscow', 'moskva', 'zelenograd', 'khimki', 'mytishchi', 'korolev',
            'lyubertsy', 'krasnogorsk', 'balashikha', 'podolsk', 'odintsovo',
            'shchyolkovo', 'dolgoprudny', 'reutov', 'lobnya', 'zhukovsky',
            'elektrostal', 'pushkino', 'sergiev posad', 'noginsk', 'orekhovo-zuyevo',
            'fryazino', 'ivanteevka', 'vidnoye', 'domodedovo', 'vnukovo'
        ],
        # Санкт-Петербург
        'saint_petersburg': [
            'saint petersburg', 'st. petersburg', 'st petersburg', 'petersburg',
            'sankt-peterburg', 'pushkin', 'kolpino', 'petrodvorets', 'lomonosov',
            'zelenogorsk', 'sestroretsk', 'kronstadt', 'gatchina', 'vsevolozhsk',
            'tosno', 'kirishi', 'kirovsk', 'murino', 'kudrovo'
        ],
        # Казань
        'kazan': [
            'kazan', 'vysokaya gora', 'zelenodolsk', 'laishevo', 'pestretsy'
        ],
        # Новосибирск
        'novosibirsk': [
            'novosibirsk', 'berdsk', 'akademgorodok', 'ob', 'koltsovo'
        ],
        # Нижний Новгород
        'nizhny_novgorod': [
            'nizhny novgorod', 'nizhnij novgorod', 'bor', 'dzerzhinsk', 'kstovo'
        ],
        # Самара
        'samara': [
            'samara', 'togliatti', 'tolyatti', 'syzran', 'novokuybyshevsk', 'chapayevsk'
        ],
        # Ростов-на-Дону
        'rostov': [
            'rostov-on-don', 'rostov-na-donu', 'bataysk', 'aksay', 'novocherkassk', 'taganrog'
        ],
        # Красноярск
        'krasnoyarsk': [
            'krasnoyarsk', 'divnogorsk', 'sosnovoborsk', 'zheleznogorsk'
        ],
        # Челябинск
        'chelyabinsk': [
            'chelyabinsk', 'kopeysk', 'kopeisk', 'zlatoust', 'miass'
        ],
        # Уфа
        'ufa': [
            'ufa', 'sterlitamak', 'salavat', 'neftekamsk'
        ],
        # Пермь
        'perm': [
            'perm', 'krasnokamsk', 'chusovoy', 'lysva', 'berezniki'
        ],
        # Волгоград
        'volgograd': [
            'volgograd', 'volzhsky', 'volzhskiy', 'kamyshin'
        ],
        # Воронеж
        'voronezh': [
            'voronezh', 'novovoronezh', 'semiluki'
        ],
        # Краснодар
        'krasnodar': [
            'krasnodar', 'goryachy klyuch', 'dinskaya', 'korenovsk'
        ],
        # Сочи
        'sochi': [
            'sochi', 'adler', 'lazarevskoye', 'krasnaya polyana', 'dagomys', 'khosta'
        ],
    }

    # Минимальное расстояние (км), при котором города считаются "далеко" друг от друга
    MIN_DISTANCE_FOR_DIFFERENT_CITIES = 100
    
    def __init__(self, geoip_service: Optional[GeoIPService] = None):
        """
        Инициализирует GeoAnalyzer.

        Args:
            geoip_service: Сервис для получения геолокации (по умолчанию используется глобальный)
        """
        self.geoip = geoip_service or get_geoip_service()
        # Строим обратный индекс: город -> агломерация
        self._city_to_metro: Dict[str, str] = {}
        for metro_name, cities in self.METROPOLITAN_AREAS.items():
            for city in cities:
                self._city_to_metro[city.lower()] = metro_name

    def _normalize_city_name(self, city: str) -> str:
        """
        Нормализует название города для сравнения.

        Убирает диакритику, приводит к нижнему регистру, убирает лишние символы.
        """
        if not city:
            return ""
        # Приводим к нижнему регистру и убираем лишние пробелы
        normalized = city.lower().strip()
        # Убираем распространённые суффиксы
        for suffix in [' city', ' gorod', ' oblast', ' region']:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()
        return normalized

    def _get_metro_area(self, city: str) -> Optional[str]:
        """
        Возвращает название агломерации для города или None, если город не в агломерации.
        """
        if not city:
            return None
        normalized = self._normalize_city_name(city)
        return self._city_to_metro.get(normalized)

    def _are_cities_in_same_metro(self, city1: str, city2: str) -> bool:
        """
        Проверяет, находятся ли два города в одной агломерации.

        Args:
            city1: Первый город
            city2: Второй город

        Returns:
            True если города в одной агломерации или это один и тот же город
        """
        if not city1 or not city2:
            return False

        normalized1 = self._normalize_city_name(city1)
        normalized2 = self._normalize_city_name(city2)

        # Если названия идентичны после нормализации
        if normalized1 == normalized2:
            return True

        # Проверяем агломерации
        metro1 = self._city_to_metro.get(normalized1)
        metro2 = self._city_to_metro.get(normalized2)

        # Если оба города в одной агломерации
        if metro1 and metro2 and metro1 == metro2:
            return True

        return False
    
    async def _get_ip_metadata(self, ip_address: str) -> Optional[IPMetadata]:
        """
        Получить метаданные IP адреса.
        
        Args:
            ip_address: IP адрес
        
        Returns:
            IPMetadata или None
        """
        return await self.geoip.lookup(ip_address)
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Вычислить расстояние между двумя точками по формуле Haversine (км).
        
        Args:
            lat1, lon1: Координаты первой точки
            lat2, lon2: Координаты второй точки
        
        Returns:
            Расстояние в километрах
        """
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Радиус Земли в км
        
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)
        
        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        
        return R * c
    
    async def analyze(
        self,
        connections: List[ActiveConnection],
        connection_history: List[Dict[str, Any]]
    ) -> GeoScore:
        """
        Анализирует географическое распределение IP.
        
        Args:
            connections: Активные подключения
            connection_history: История подключений
        
        Returns:
            GeoScore с оценкой и причинами
        """
        score = 0.0
        reasons = []
        countries: Set[str] = set()
        cities: Set[str] = set()
        impossible_travel = False
        
        # Собираем уникальные IP из активных подключений и истории
        all_ips = set()
        for conn in connections:
            all_ips.add(str(conn.ip_address))
        for conn in connection_history:
            ip = str(conn.get("ip_address", ""))
            if ip:
                all_ips.add(ip)
        
        # Получаем метаданные для всех IP одним batch запросом (оптимизировано)
        ip_metadata: Dict[str, IPMetadata] = await self.geoip.lookup_batch(list(all_ips))

        for ip, metadata in ip_metadata.items():
            # Debug: логируем данные для каждого IP
            logger.debug(
                "GeoIP for %s: country=%s, city=%s, region=%s, asn=%s (%s), connection_type=%s, coords=(%s, %s)",
                ip, metadata.country_code, metadata.city, metadata.region,
                metadata.asn, metadata.asn_org, metadata.connection_type,
                metadata.latitude, metadata.longitude
            )
            if metadata.country_code:
                countries.add(metadata.country_code)
            if metadata.city:
                cities.add(metadata.city)
        
        # Если нет данных о геолокации, возвращаем нулевой скор
        # Не добавляем это в причины, так как отсутствие данных не является нарушением
        if not ip_metadata:
            return GeoScore(
                score=0.0,
                reasons=[],
                countries=countries,
                cities=cities,
                impossible_travel_detected=False
            )
        
        # Анализ одновременных подключений с разных стран
        active_countries = set()
        for conn in connections:
            ip = str(conn.ip_address)
            if ip in ip_metadata:
                country = ip_metadata[ip].country_code
                if country:
                    active_countries.add(country)
        
        if len(active_countries) > 1:
            score = 90.0
            reasons.append(f"Одновременные подключения из разных стран: {', '.join(active_countries)}")
            impossible_travel = True
        
        # Анализ последовательных подключений
        if len(connection_history) > 1 and not impossible_travel:
            sorted_history = sorted(
                connection_history,
                key=lambda x: x.get("connected_at") or datetime.min
            )
            
            for i in range(1, len(sorted_history)):
                prev_conn = sorted_history[i - 1]
                curr_conn = sorted_history[i]
                
                prev_ip = str(prev_conn.get("ip_address", ""))
                curr_ip = str(curr_conn.get("ip_address", ""))
                
                if prev_ip not in ip_metadata or curr_ip not in ip_metadata:
                    continue
                
                prev_meta = ip_metadata[prev_ip]
                curr_meta = ip_metadata[curr_ip]
                
                prev_country = prev_meta.country_code or ""
                curr_country = curr_meta.country_code or ""
                prev_city = prev_meta.city or ""
                curr_city = curr_meta.city or ""
                prev_lat = prev_meta.latitude
                prev_lon = prev_meta.longitude
                curr_lat = curr_meta.latitude
                curr_lon = curr_meta.longitude
                
                # Разные страны
                if prev_country != curr_country and prev_country and curr_country:
                    prev_time = prev_conn.get("connected_at")
                    curr_time = curr_conn.get("connected_at")
                    
                    if prev_time and curr_time:
                        # Преобразуем в datetime
                        if isinstance(prev_time, str):
                            try:
                                prev_time = datetime.fromisoformat(prev_time.replace('Z', '+00:00'))
                            except ValueError:
                                continue
                        if isinstance(curr_time, str):
                            try:
                                curr_time = datetime.fromisoformat(curr_time.replace('Z', '+00:00'))
                            except ValueError:
                                continue
                        
                        if isinstance(prev_time, datetime) and isinstance(curr_time, datetime):
                            if prev_time.tzinfo:
                                prev_time = prev_time.replace(tzinfo=None)
                            if curr_time.tzinfo:
                                curr_time = curr_time.replace(tzinfo=None)
                            
                            time_diff_hours = (curr_time - prev_time).total_seconds() / 3600
                            
                            # Проверяем реалистичность перемещения используя реальные координаты
                            if prev_lat and prev_lon and curr_lat and curr_lon:
                                distance_km = self._haversine_distance(prev_lat, prev_lon, curr_lat, curr_lon)
                                max_distance_km = self.TRAVEL_SPEEDS['international'] * time_diff_hours
                                
                                if distance_km > max_distance_km:
                                    score = max(score, 50.0)
                                    reasons.append(
                                        f"Нереалистичное перемещение: {prev_country} → {curr_country} "
                                        f"({distance_km:.0f} км за {time_diff_hours:.1f} ч, макс: {max_distance_km:.0f} км)"
                                    )
                                    impossible_travel = True
                                else:
                                    score = max(score, 15.0)
                                    reasons.append(f"Перемещение между странами: {prev_country} → {curr_country}")
                            else:
                                # Если нет координат, используем эвристику
                                if time_diff_hours < 1:
                                    score = max(score, 50.0)
                                    reasons.append(
                                        f"Нереалистичное перемещение: {prev_country} → {curr_country} за {time_diff_hours:.1f} ч"
                                    )
                                    impossible_travel = True
                                else:
                                    score = max(score, 15.0)
                                    reasons.append(f"Перемещение между странами: {prev_country} → {curr_country}")
                
                # Разные города одной страны
                elif prev_country == curr_country and prev_city != curr_city and prev_city and curr_city:
                    # Проверяем, находятся ли города в одной агломерации (пригороды)
                    # Если да, это нормальное поведение - не добавляем скор
                    if self._are_cities_in_same_metro(prev_city, curr_city):
                        # Города в одной агломерации - это нормально (пригороды, районы города)
                        # Не добавляем скор и не добавляем причину
                        pass
                    else:
                        # Города в разных регионах - проверяем расстояние
                        # Если есть координаты, проверяем реальное расстояние
                        if prev_lat and prev_lon and curr_lat and curr_lon:
                            distance_km = self._haversine_distance(prev_lat, prev_lon, curr_lat, curr_lon)
                            # Градуированная оценка по расстоянию:
                            # < 50 км: 0 (очень близко, вероятно погрешность GeoIP или пригород)
                            # 50-100 км: 2 (умеренно близко)
                            # > 100 км: 5 (разные регионы)
                            if distance_km <= 50:
                                # Очень близко - игнорируем (возможно погрешность GeoIP)
                                pass
                            elif distance_km <= self.MIN_DISTANCE_FOR_DIFFERENT_CITIES:
                                # Умеренно близко - минимальный скор
                                score = max(score, 2.0)
                                if not reasons:
                                    reasons.append(f"Близкие города: {prev_city} → {curr_city} ({distance_km:.0f} км)")
                            else:
                                # Далеко - стандартный скор
                                score = max(score, 5.0)
                                if not reasons:
                                    reasons.append(f"Разные города одной страны: {prev_city} → {curr_city} ({distance_km:.0f} км)")
                        else:
                            # Нет координат - добавляем минимальный скор на всякий случай
                            score = max(score, 3.0)
                            if not reasons:
                                reasons.append(f"Разные города одной страны: {prev_city} → {curr_city}")
        
        return GeoScore(
            score=min(score, 100.0),
            reasons=reasons,
            countries=countries,
            cities=cities,
            impossible_travel_detected=impossible_travel
        )


class ASNAnalyzer:
    """
    Анализ типа интернет-провайдера (ASN).
    
    Использует локальную базу ASN по РФ для более точного определения типа провайдера.
    
    Детальная классификация типов провайдеров:
    - mobile: Точно мобильные пулы (CGNAT, LTE, GPRS) - ×0.3 модификатор (низкая подозрительность)
    - mobile_isp: Сети мобильных операторов (MegaFon, MTS, Beeline, Tele2) - ×0.5 модификатор
    - fixed: Проводной ШПД (Broadband, DSL, GPON) - ×0.8 модификатор (норма)
    - isp: Крупные провайдеры (ER-Telecom, ТТК, Ростелеком) - ×1.0 модификатор (стандартный)
    - regional_isp: Региональные ISP - ×1.0 модификатор (стандартный)
    - business: Корпоративные (Yandex, Mail.ru) - ×1.2 модификатор (повышенное внимание)
    - hosting: Хостинг (Selectel, Timeweb, Beget, VDSina) - ×1.5 модификатор (высокое внимание)
    - infrastructure: Магистральная инфраструктура - ×1.3 модификатор
    - vpn: VPN/Proxy - ×1.8 модификатор (очень высокое внимание)
    """
    
    # Модификаторы подозрительности для разных типов провайдеров
    PROVIDER_TYPE_MODIFIERS = {
        'mobile': 0.3,           # Мобильные пулы - очень низкая подозрительность
        'mobile_isp': 0.5,       # Мобильные операторы - низкая подозрительность
        'fixed': 0.8,           # Проводной ШПД - норма
        'isp': 1.0,             # Крупные провайдеры - стандарт
        'regional_isp': 1.0,     # Региональные ISP - стандарт
        'residential': 1.0,      # Домашние (legacy) - стандарт
        'business': 1.2,        # Корпоративные - повышенное внимание
        'infrastructure': 1.3,   # Магистральная инфраструктура - повышенное внимание
        'hosting': 1.5,         # Хостинг - высокое внимание
        'datacenter': 1.5,      # Датацентр (legacy) - высокое внимание
        'vpn': 1.8,             # VPN/Proxy - очень высокое внимание
        'unknown': 1.0,         # Неизвестный тип - стандарт
    }
    
    # Типы провайдеров, которые считаются мобильными
    MOBILE_TYPES = {'mobile', 'mobile_isp'}
    
    # Типы провайдеров, которые считаются датацентрами/хостингом
    DATACENTER_TYPES = {'hosting', 'datacenter'}
    
    # Типы провайдеров, которые считаются VPN
    VPN_TYPES = {'vpn'}
    
    def __init__(self, geoip_service: Optional[GeoIPService] = None, db_service: Optional[DatabaseService] = None):
        """
        Инициализирует ASNAnalyzer.
        
        Args:
            geoip_service: Сервис для получения метаданных IP (по умолчанию используется глобальный)
            db_service: Сервис для работы с БД (для доступа к базе ASN)
        """
        self.geoip = geoip_service or get_geoip_service()
        from src.services.database import db_service as global_db_service
        self.db = db_service or global_db_service
    
    async def analyze(
        self,
        connections: List[ActiveConnection],
        connection_history: List[Dict[str, Any]]
    ) -> ASNScore:
        """
        Анализирует типы провайдеров для IP адресов.
        
        Args:
            connections: Активные подключения
            connection_history: История подключений
        
        Returns:
            ASNScore с оценкой и причинами
        """
        score = 0.0
        reasons = []
        asn_types: Set[str] = set()
        is_mobile_carrier = False
        is_datacenter = False
        is_vpn = False
        
        # Собираем уникальные IP
        all_ips = set()
        for conn in connections:
            all_ips.add(str(conn.ip_address))
        for conn in connection_history:
            ip = str(conn.get("ip_address", ""))
            if ip:
                all_ips.add(ip)
        
        # Получаем метаданные для всех IP одним batch запросом (оптимизировано)
        ip_metadata: Dict[str, IPMetadata] = await self.geoip.lookup_batch(list(all_ips))
        
        if not ip_metadata:
            return ASNScore(
                score=0.0,
                reasons=[],
                asn_types=asn_types,
                is_mobile_carrier=False,
                is_datacenter=False,
                is_vpn=False
            )
        
        # Анализируем типы провайдеров с детальной классификацией
        provider_type_counts: Dict[str, int] = {}
        mobile_count = 0
        datacenter_count = 0
        vpn_count = 0
        business_count = 0
        infrastructure_count = 0
        
        for metadata in ip_metadata.values():
            if metadata.connection_type:
                asn_types.add(metadata.connection_type)
                provider_type = metadata.connection_type
                
                # Подсчитываем по типам
                provider_type_counts[provider_type] = provider_type_counts.get(provider_type, 0) + 1
                
                # Определяем категории для обратной совместимости
                if provider_type in self.MOBILE_TYPES:
                    mobile_count += 1
                    is_mobile_carrier = True
                elif provider_type in self.DATACENTER_TYPES:
                    datacenter_count += 1
                    is_datacenter = True
                elif provider_type in self.VPN_TYPES:
                    vpn_count += 1
                    is_vpn = True
                elif provider_type == 'business':
                    business_count += 1
                elif provider_type == 'infrastructure':
                    infrastructure_count += 1
        
        # Оценка на основе типов провайдеров в активных подключениях
        active_ips = {str(conn.ip_address) for conn in connections}
        active_provider_types: Dict[str, int] = {}
        
        for ip, meta in ip_metadata.items():
            if ip in active_ips and meta.connection_type:
                provider_type = meta.connection_type
                active_provider_types[provider_type] = active_provider_types.get(provider_type, 0) + 1
        
        # Подсчитываем подозрительные типы в активных подключениях
        active_datacenter_count = sum(
            count for ptype, count in active_provider_types.items()
            if ptype in self.DATACENTER_TYPES
        )
        active_vpn_count = sum(
            count for ptype, count in active_provider_types.items()
            if ptype in self.VPN_TYPES
        )
        active_business_count = sum(
            count for ptype, count in active_provider_types.items()
            if ptype == 'business'
        )
        active_infrastructure_count = sum(
            count for ptype, count in active_provider_types.items()
            if ptype == 'infrastructure'
        )
        
        # Оценка на основе типов провайдеров
        # Хостинг/датацентры - очень подозрительно
        if active_datacenter_count > 0:
            score += 25.0
            reasons.append(f"Подключения через хостинг/датацентр ({active_datacenter_count} IP)")
        
        # VPN - подозрительно
        if active_vpn_count > 0:
            score += 15.0
            reasons.append(f"Подключения через VPN ({active_vpn_count} IP)")
        
        # Корпоративные сети - умеренно подозрительно (может быть шаринг)
        if active_business_count > 0:
            score += 10.0
            reasons.append(f"Подключения через корпоративные сети ({active_business_count} IP)")
        
        # Магистральная инфраструктура - редко используется конечными пользователями
        if active_infrastructure_count > 0:
            score += 8.0
            reasons.append(f"Подключения через магистральную инфраструктуру ({active_infrastructure_count} IP)")
        
        # Если большинство подключений через подозрительные типы - более критично
        if len(active_ips) > 0:
            suspicious_count = active_datacenter_count + active_vpn_count + active_business_count
            suspicious_ratio = suspicious_count / len(active_ips)
            
            if suspicious_ratio > 0.7:
                score += 20.0
                reasons.append(f"Большинство подключений через подозрительные типы провайдеров ({suspicious_ratio*100:.0f}%)")
            elif suspicious_ratio > 0.5:
                score += 10.0
                reasons.append(f"Много подключений через подозрительные типы провайдеров ({suspicious_ratio*100:.0f}%)")
        
        return ASNScore(
            score=min(score, 100.0),
            reasons=reasons,
            asn_types=asn_types,
            is_mobile_carrier=is_mobile_carrier,
            is_datacenter=is_datacenter,
            is_vpn=is_vpn
        )


class UserProfileAnalyzer:
    """
    Анализ отклонений от исторического профиля пользователя.
    
    Строит baseline на основе истории подключений и сравнивает текущее поведение.
    """
    
    def __init__(self, db_service: DatabaseService):
        """
        Инициализирует UserProfileAnalyzer.
        
        Args:
            db_service: Сервис для работы с БД
        """
        self.db = db_service
    
    async def build_baseline(self, user_uuid: str, days: int = 30) -> Dict[str, Any]:
        """
        Строит baseline профиль пользователя на основе истории.
        
        Args:
            user_uuid: UUID пользователя
            days: Количество дней истории для анализа
        
        Returns:
            Словарь с baseline данными
        """
        try:
            history = await self.db.get_connection_history(user_uuid, days=days)
            
            if not history:
                return {
                    'typical_countries': [],
                    'typical_cities': [],
                    'typical_regions': [],
                    'typical_asns': [],
                    'known_ips': [],
                    'avg_daily_unique_ips': 0.0,
                    'max_daily_unique_ips': 0,
                    'typical_hours': [],
                    'avg_session_duration_minutes': 0,
                    'data_points': 0
                }
            
            # Группируем по дням
            from collections import defaultdict
            daily_ips: Dict[str, Set[str]] = defaultdict(set)
            all_known_ips: Set[str] = set()  # Все IP, которые пользователь использовал
            countries: Set[str] = set()
            cities: Set[str] = set()
            regions: Set[str] = set()  # Регионы (области)
            asns: Set[str] = set()
            hours: List[int] = []
            session_durations: List[float] = []

            for conn in history:
                ip = str(conn.get("ip_address", ""))
                connected_at = conn.get("connected_at")
                disconnected_at = conn.get("disconnected_at")

                # Собираем известные IP
                if ip:
                    all_known_ips.add(ip)

                # Собираем гео-данные если есть в истории
                country = conn.get("country") or conn.get("country_code")
                city = conn.get("city")
                region = conn.get("region")
                asn = conn.get("asn") or conn.get("asn_org")

                if country:
                    countries.add(str(country))
                if city:
                    cities.add(str(city))
                if region:
                    regions.add(str(region))
                if asn:
                    asns.add(str(asn))

                if connected_at:
                    if isinstance(connected_at, str):
                        try:
                            connected_at = datetime.fromisoformat(connected_at.replace('Z', '+00:00'))
                        except ValueError:
                            continue

                    if isinstance(connected_at, datetime):
                        day_key = connected_at.strftime('%Y-%m-%d')
                        daily_ips[day_key].add(ip)

                        hour = connected_at.hour
                        hours.append(hour)

                        # Вычисляем длительность сессии
                        if disconnected_at:
                            if isinstance(disconnected_at, str):
                                try:
                                    disconnected_at = datetime.fromisoformat(disconnected_at.replace('Z', '+00:00'))
                                except ValueError:
                                    disconnected_at = None

                            if isinstance(disconnected_at, datetime):
                                duration_minutes = (disconnected_at - connected_at).total_seconds() / 60
                                if duration_minutes > 0:
                                    session_durations.append(duration_minutes)
            
            # Вычисляем средние значения
            daily_unique_ips = [len(ips) for ips in daily_ips.values()]
            avg_daily_unique_ips = sum(daily_unique_ips) / len(daily_unique_ips) if daily_unique_ips else 0.0
            max_daily_unique_ips = max(daily_unique_ips) if daily_unique_ips else 0
            
            # Типичные часы (часы с наибольшей активностью)
            from collections import Counter
            hour_counts = Counter(hours)
            typical_hours = [hour for hour, _ in hour_counts.most_common(8)]  # Топ-8 часов
            
            avg_session_duration = sum(session_durations) / len(session_durations) if session_durations else 0
            
            return {
                'typical_countries': list(countries),
                'typical_cities': list(cities),
                'typical_regions': list(regions),
                'typical_asns': list(asns),
                'known_ips': list(all_known_ips),  # IP, которые пользователь уже использовал
                'avg_daily_unique_ips': avg_daily_unique_ips,
                'max_daily_unique_ips': max_daily_unique_ips,
                'typical_hours': typical_hours,
                'avg_session_duration_minutes': avg_session_duration,
                'data_points': len(daily_ips)
            }

        except Exception as e:
            logger.error("Error building baseline for user %s: %s", user_uuid, e, exc_info=True)
            return {
                'typical_countries': [],
                'typical_cities': [],
                'typical_regions': [],
                'typical_asns': [],
                'known_ips': [],
                'avg_daily_unique_ips': 0.0,
                'max_daily_unique_ips': 0,
                'typical_hours': [],
                'avg_session_duration_minutes': 0,
                'data_points': 0
            }
    
    async def analyze(
        self,
        user_uuid: str,
        current_ips: Set[str],
        current_countries: Set[str],
        baseline: Optional[Dict[str, Any]] = None
    ) -> ProfileScore:
        """
        Анализирует отклонения от baseline профиля.
        
        Args:
            user_uuid: UUID пользователя
            current_ips: Текущие уникальные IP
            current_countries: Текущие страны
            baseline: Baseline профиль (если None, будет построен автоматически)
        
        Returns:
            ProfileScore с оценкой и причинами
        """
        score = 0.0
        reasons = []
        deviation = 0.0
        
        if baseline is None:
            baseline = await self.build_baseline(user_uuid, days=30)
        
        # Если недостаточно данных для baseline, возвращаем нулевой скор
        if baseline['data_points'] < 7:  # Минимум неделя данных
            return ProfileScore(
                score=0.0,
                reasons=[],
                deviation_from_baseline=0.0
            )
        
        # Проверяем, сколько текущих IP уже известны пользователю
        known_ips = set(baseline.get('known_ips', []))
        if current_ips and known_ips:
            known_current_ips = current_ips & known_ips
            known_ratio = len(known_current_ips) / len(current_ips) if current_ips else 0

            # Если все или большинство IP известны, это очень хороший знак
            if known_ratio >= 0.8:
                # Почти все IP известны - минимальный скор
                # Это означает, что пользователь использует те же IP, что и раньше
                return ProfileScore(
                    score=0.0,
                    reasons=[],
                    deviation_from_baseline=0.0
                )
            elif known_ratio >= 0.5:
                # Половина IP известны - снижаем потенциальный скор
                # Будем применять модификатор 0.5 к итоговому скору
                pass  # Продолжаем анализ, но учтём это позже

        # Сравниваем количество уникальных IP
        current_unique_ips = len(current_ips)
        avg_daily_ips = baseline['avg_daily_unique_ips']
        max_daily_ips = baseline['max_daily_unique_ips']

        if avg_daily_ips > 0:
            deviation_ratio = current_unique_ips / avg_daily_ips

            if deviation_ratio > 2.0:
                score = 45.0
                reasons.append(f"Аномалия: обычно {avg_daily_ips:.1f} IP/день, сейчас {current_unique_ips}")
                deviation = deviation_ratio
            elif deviation_ratio > 1.5:
                score = 30.0
                reasons.append(f"Отклонение: обычно {avg_daily_ips:.1f} IP/день, сейчас {current_unique_ips}")
                deviation = deviation_ratio
            elif current_unique_ips > max_daily_ips:
                score = 15.0
                reasons.append(f"Превышен максимум: обычно макс {max_daily_ips} IP/день, сейчас {current_unique_ips}")
                deviation = current_unique_ips / max_daily_ips if max_daily_ips > 0 else 0

        # Проверяем новые страны (только если baseline содержит страны)
        typical_countries = set(baseline.get('typical_countries', []))
        if typical_countries:  # Только если есть данные о типичных странах
            new_countries = current_countries - typical_countries
            if new_countries:
                score += 20.0
                reasons.append(f"Новая страна (первый раз): {', '.join(new_countries)}")

        # Если половина IP известны, снижаем скор
        if current_ips and known_ips:
            known_ratio = len(current_ips & known_ips) / len(current_ips)
            if known_ratio >= 0.5:
                score *= 0.5  # Снижаем на 50% если половина IP известны
        
        return ProfileScore(
            score=min(score, 100.0),
            reasons=reasons,
            deviation_from_baseline=deviation
        )


class DeviceFingerprintAnalyzer:
    """
    Анализ устройств по fingerprint (User-Agent и другие данные).
    
    Правила:
    - Один fingerprint, разные IP = 0 (один человек, разные сети)
    - Разные версии одного клиента = +10
    - Разные клиенты = +25
    - Разные ОС = +40
    - > 3 разных fingerprint одновременно = +60
    """
    
    def _extract_fingerprint(self, connection: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Извлекает fingerprint из данных подключения.
        
        Args:
            connection: Данные подключения
        
        Returns:
            Словарь с fingerprint данными или None
        """
        device_info = connection.get("device_info")
        user_agent = connection.get("user_agent")
        
        if not device_info and not user_agent:
            return None
        
        fingerprint = {}
        
        # Парсим User-Agent если доступен
        if user_agent:
            fingerprint['user_agent'] = user_agent
            # Простой парсинг User-Agent для определения ОС и клиента
            ua_lower = user_agent.lower()
            
            # Определяем ОС
            if 'android' in ua_lower:
                fingerprint['os_family'] = 'Android'
            elif 'ios' in ua_lower or 'iphone' in ua_lower or 'ipad' in ua_lower:
                fingerprint['os_family'] = 'iOS'
            elif 'windows' in ua_lower:
                fingerprint['os_family'] = 'Windows'
            elif 'linux' in ua_lower:
                fingerprint['os_family'] = 'Linux'
            elif 'macos' in ua_lower or 'mac os' in ua_lower:
                fingerprint['os_family'] = 'macOS'
            else:
                fingerprint['os_family'] = 'Unknown'
            
            # Определяем клиент
            if 'v2rayng' in ua_lower or 'v2ray' in ua_lower:
                fingerprint['client_type'] = 'V2RayNG'
            elif 'shadowrocket' in ua_lower:
                fingerprint['client_type'] = 'Shadowrocket'
            elif 'clash' in ua_lower:
                fingerprint['client_type'] = 'Clash'
            elif 'surge' in ua_lower:
                fingerprint['client_type'] = 'Surge'
            else:
                fingerprint['client_type'] = 'Unknown'
        
        # Используем device_info если доступен
        if device_info:
            if isinstance(device_info, dict):
                fingerprint.update(device_info)
            elif isinstance(device_info, str):
                # Пытаемся распарсить JSON строку
                try:
                    import json
                    device_dict = json.loads(device_info)
                    fingerprint.update(device_dict)
                except (json.JSONDecodeError, TypeError):
                    fingerprint['device_info_raw'] = device_info
        
        return fingerprint if fingerprint else None
    
    def analyze(
        self,
        connections: List[ActiveConnection],
        connection_history: List[Dict[str, Any]]
    ) -> DeviceScore:
        """
        Анализирует fingerprint устройств.
        
        Args:
            connections: Активные подключения
            connection_history: История подключений
        
        Returns:
            DeviceScore с оценкой и причинами
        """
        score = 0.0
        reasons = []
        
        # Собираем все подключения для анализа
        all_connections = []
        for conn in connections:
            all_connections.append({
                'ip_address': str(conn.ip_address),
                'device_info': getattr(conn, 'device_info', None),
                'user_agent': getattr(conn, 'user_agent', None)
            })
        
        for conn in connection_history:
            all_connections.append(conn)
        
        # Извлекаем fingerprint для каждого подключения
        fingerprints: List[Dict[str, str]] = []
        for conn in all_connections:
            fp = self._extract_fingerprint(conn)
            if fp:
                fingerprints.append(fp)
        
        if not fingerprints:
            return DeviceScore(
                score=0.0,
                reasons=[],
                unique_fingerprints_count=0,
                different_os_count=0
            )
        
        # Группируем по уникальным fingerprint
        unique_fingerprints: List[Dict[str, str]] = []
        seen_fps = set()
        
        for fp in fingerprints:
            # Создаём ключ для сравнения fingerprint
            fp_key = (
                fp.get('os_family', ''),
                fp.get('client_type', ''),
                fp.get('user_agent', '')[:100]  # Первые 100 символов User-Agent
            )
            
            if fp_key not in seen_fps:
                seen_fps.add(fp_key)
                unique_fingerprints.append(fp)
        
        unique_fingerprints_count = len(unique_fingerprints)
        
        # Подсчитываем уникальные ОС (исключаем Unknown)
        os_families = set(fp.get('os_family', 'Unknown') for fp in unique_fingerprints)
        os_families_known = sorted([os for os in os_families if os and os != 'Unknown'])
        different_os_count = len(os_families)

        # Подсчитываем уникальные клиенты (исключаем Unknown)
        client_types = set(fp.get('client_type', 'Unknown') for fp in unique_fingerprints)
        client_types_known = sorted([client for client in client_types if client and client != 'Unknown'])
        different_clients_count = len(client_types)

        # Оценка на основе различий
        if unique_fingerprints_count > 3:
            score = 60.0
            reasons.append(f"Много разных устройств одновременно ({unique_fingerprints_count} fingerprint)")
        elif different_os_count >= 3:
            score = 40.0
            reasons.append(f"Разные ОС одновременно: {', '.join(os_families)}")
        elif different_clients_count >= 2:
            score = 25.0
            reasons.append(f"Разные клиенты: {', '.join(client_types)}")
        elif unique_fingerprints_count > 1:
            # Проверяем, есть ли разные версии одного клиента
            if different_clients_count == 1 and unique_fingerprints_count > 1:
                score = 10.0
                reasons.append(f"Разные версии одного клиента ({unique_fingerprints_count} fingerprint)")

        return DeviceScore(
            score=min(score, 100.0),
            reasons=reasons,
            unique_fingerprints_count=unique_fingerprints_count,
            different_os_count=different_os_count,
            os_list=os_families_known if os_families_known else None,
            client_list=client_types_known if client_types_known else None
        )


class IntelligentViolationDetector:
    """
    Система многофакторного анализа для детектирования нарушений.
    
    Объединяет результаты всех анализаторов и вычисляет итоговый скор нарушения.
    """
    
    # Веса факторов
    WEIGHTS = {
        'temporal': 0.25,      # Временной паттерн
        'geo': 0.25,           # География
        'asn': 0.15,           # Тип провайдера
        'profile': 0.20,        # Отклонение от профиля
        'device': 0.15,        # Fingerprint устройств
    }
    
    # Пороги для действий
    THRESHOLDS = {
        'no_action': 30,       # < 30: ничего не делаем
        'monitor': 50,         # 30-50: усиленный мониторинг
        'warn': 65,            # 50-65: предупреждение пользователю
        'soft_block': 80,      # 65-80: мягкая блокировка (ограничение скорости)
        'temp_block': 90,      # 80-90: временная блокировка
        'hard_block': 95,      # > 95: блокировка + ручная проверка
    }
    
    def __init__(self, db_service: DatabaseService, connection_monitor: ConnectionMonitor, geoip_service: Optional[GeoIPService] = None):
        """
        Инициализирует IntelligentViolationDetector.
        
        Args:
            db_service: Сервис для работы с БД
            connection_monitor: Сервис для мониторинга подключений
            geoip_service: Сервис для получения геолокации (по умолчанию используется глобальный)
        """
        self.db = db_service
        self.connection_monitor = connection_monitor
        geoip = geoip_service or get_geoip_service()
        self.temporal_analyzer = TemporalAnalyzer()
        self.geo_analyzer = GeoAnalyzer(geoip_service=geoip)
        self.asn_analyzer = ASNAnalyzer(geoip_service=geoip)
        self.profile_analyzer = UserProfileAnalyzer(db_service)
        self.device_analyzer = DeviceFingerprintAnalyzer()
    
    async def check_user(self, user_uuid: str, window_minutes: int = 60) -> Optional[ViolationScore]:
        """
        Проверить пользователя на нарушения.
        
        Args:
            user_uuid: UUID пользователя
            window_minutes: Временное окно для анализа (по умолчанию 60 минут)
        
        Returns:
            ViolationScore или None при ошибке
        """
        if not self.db.is_connected:
            logger.warning("Database not connected, cannot check user violations")
            return None
        
        try:
            # Получаем количество устройств пользователя из локальной БД
            user_device_count = await self.db.get_user_devices_count(user_uuid)
            
            # Получаем активные подключения (только за последние 5 минут)
            # Это учитывает роутинг в приложении - старые подключения не считаются активными
            active_connections = await self.connection_monitor.get_user_active_connections(user_uuid, max_age_minutes=5)

            # Получаем историю подключений
            history_days = max(1, window_minutes // (24 * 60) + 1)
            connection_history = await self.db.get_connection_history(user_uuid, days=history_days)

            # Добавляем debug-логирование для диагностики
            logger.info(
                "Violation check for user %s: device_count=%d, active_connections=%d, history_records=%d",
                user_uuid, user_device_count, len(active_connections), len(connection_history)
            )
            for i, conn in enumerate(active_connections):
                logger.debug(
                    "  Active connection %d: ip=%s, connected_at=%s",
                    i + 1, conn.ip_address, conn.connected_at
                )

            # Анализируем временные паттерны (передаём количество устройств)
            temporal_score = self.temporal_analyzer.analyze(active_connections, connection_history, user_device_count)
            
            # Анализируем геолокацию (async)
            geo_score = await self.geo_analyzer.analyze(active_connections, connection_history)

            # Debug-логирование гео-данных для диагностики проблем с городами
            logger.info(
                "Geo analysis for user %s: countries=%s, cities=%s, score=%.1f",
                user_uuid, geo_score.countries, geo_score.cities, geo_score.score
            )
            if geo_score.reasons:
                for reason in geo_score.reasons:
                    logger.info("  Geo reason: %s", reason)

            # Анализируем тип провайдера (ASN) (async)
            asn_score = await self.asn_analyzer.analyze(active_connections, connection_history)
            
            # Анализируем отклонения от профиля (async)
            current_ips = {str(conn.ip_address) for conn in active_connections}
            current_countries = geo_score.countries
            profile_score = await self.profile_analyzer.analyze(user_uuid, current_ips, current_countries)
            
            # Анализируем fingerprint устройств
            device_score = self.device_analyzer.analyze(active_connections, connection_history)
            
            # Вычисляем взвешенный скор
            raw_score = (
                temporal_score.score * self.WEIGHTS['temporal'] +
                geo_score.score * self.WEIGHTS['geo'] +
                asn_score.score * self.WEIGHTS['asn'] +
                profile_score.score * self.WEIGHTS['profile'] +
                device_score.score * self.WEIGHTS['device']
            )
            
            # Применяем модификаторы на основе типов провайдеров
            # Используем средний модификатор для всех типов провайдеров в подключениях
            if asn_score.asn_types:
                modifiers = []
                for provider_type in asn_score.asn_types:
                    modifier = self.asn_analyzer.PROVIDER_TYPE_MODIFIERS.get(
                        provider_type,
                        self.asn_analyzer.PROVIDER_TYPE_MODIFIERS['unknown']
                    )
                    modifiers.append(modifier)
                
                # Используем средний модификатор (взвешенный по количеству подключений)
                avg_modifier = sum(modifiers) / len(modifiers) if modifiers else 1.0
                score_before_modifier = raw_score
                raw_score *= avg_modifier
                
                logger.debug(
                    "Applied ASN modifier %.2f for provider types: %s (score: %.2f -> %.2f)",
                    avg_modifier, ', '.join(asn_score.asn_types), score_before_modifier, raw_score
                )
            else:
                # Fallback для обратной совместимости
                if asn_score.is_mobile_carrier:
                    raw_score *= 0.5  # Снижаем для мобильных операторов
                elif asn_score.is_datacenter:
                    raw_score *= 1.5  # Повышаем для датацентров
                elif asn_score.is_vpn:
                    raw_score *= 1.8  # Сильно повышаем для VPN
            
            # Детекция паттерна переключения сетей (Mobile <-> WiFi)
            # Если обнаружен такой паттерн, значительно снижаем скор,
            # т.к. это нормальное поведение пользователя
            is_network_switch = self._detect_network_switch_pattern(asn_score.asn_types)
            if is_network_switch:
                # Снижаем скор на 50% если это похоже на переключение сетей
                score_before_switch = raw_score
                raw_score *= 0.5
                logger.debug(
                    "Network switch pattern detected (mobile + home ISP), reducing score: %.2f -> %.2f",
                    score_before_switch, raw_score
                )

            # Проверяем, от одного ли провайдера (ASN) все IP
            # Если да, это снижает вероятность шаринга
            is_same_asn, asn_ratio = await self._check_same_asn_pattern(active_connections, connection_history)
            if is_same_asn and asn_ratio >= 0.8:
                # Все IP от одного провайдера - снижаем скор
                score_before_asn = raw_score
                raw_score *= 0.7  # 30% снижение
                logger.debug(
                    "Same ASN pattern detected (%.0f%% from same provider), reducing score: %.2f -> %.2f",
                    asn_ratio * 100, score_before_asn, raw_score
                )

            # Если есть серьёзные одновременные подключения (высокий скор), устанавливаем минимум
            # Но только если temporal_score достаточно высокий (80+), что указывает на реальное нарушение
            # Не применяем минимум для пограничных случаев (переключение сетей, несколько устройств)
            # И не применяем если обнаружен паттерн переключения сетей
            if not is_network_switch:
                if temporal_score.score >= 80.0 and temporal_score.simultaneous_connections_count > 1:
                    raw_score = max(raw_score, 85.0)
                elif temporal_score.score >= 40.0 and temporal_score.simultaneous_connections_count > 1:
                    # Пограничные случаи - устанавливаем минимум для мониторинга, но не блокировки
                    raw_score = max(raw_score, 50.0)
            
            # Определяем рекомендуемое действие
            recommended_action = self._get_action(raw_score)
            
            # Вычисляем уверенность (пока упрощённо)
            confidence = min(1.0, raw_score / 100.0)
            
            # Собираем все причины
            all_reasons = []
            all_reasons.extend(temporal_score.reasons)
            all_reasons.extend(geo_score.reasons)
            all_reasons.extend(asn_score.reasons)
            all_reasons.extend(profile_score.reasons)
            all_reasons.extend(device_score.reasons)
            
            return ViolationScore(
                total=min(raw_score, 100.0),
                breakdown={
                    'temporal': temporal_score,
                    'geo': geo_score,
                    'asn': asn_score,
                    'profile': profile_score,
                    'device': device_score,
                },
                recommended_action=recommended_action,
                confidence=confidence,
                reasons=all_reasons
            )
            
        except Exception as e:
            logger.error(
                "Error checking user violations for %s: %s",
                user_uuid,
                e,
                exc_info=True
            )
            return None
    
    def _detect_network_switch_pattern(self, asn_types: Set[str]) -> bool:
        """
        Определить, выглядит ли паттерн подключений как переключение сетей (WiFi <-> Mobile).

        Паттерн переключения сетей:
        - Есть мобильный провайдер (mobile, mobile_isp) И
        - Есть домашний/проводной провайдер (fixed, isp, residential, regional_isp)

        Это типичная ситуация когда пользователь переключается между WiFi дома и мобильным интернетом.

        Args:
            asn_types: Множество типов провайдеров в подключениях

        Returns:
            True если паттерн похож на переключение сетей
        """
        mobile_types = {'mobile', 'mobile_isp'}
        home_types = {'fixed', 'isp', 'residential', 'regional_isp'}

        has_mobile = bool(asn_types & mobile_types)
        has_home = bool(asn_types & home_types)

        return has_mobile and has_home

    async def _check_same_asn_pattern(
        self,
        connections: List[ActiveConnection],
        connection_history: List[Dict[str, Any]]
    ) -> tuple[bool, float]:
        """
        Проверить, принадлежат ли IP одному провайдеру (ASN).

        Если все или большинство IP от одного провайдера, это снижает вероятность шаринга,
        т.к. один пользователь обычно использует одного провайдера (особенно мобильного).

        Returns:
            Tuple (is_same_asn, ratio) где:
            - is_same_asn: True если большинство IP от одного провайдера
            - ratio: доля IP от основного провайдера (0.0 - 1.0)
        """
        # Собираем все уникальные IP
        all_ips = set()
        for conn in connections:
            all_ips.add(str(conn.ip_address))
        for conn in connection_history[-10:]:  # Последние 10 записей
            ip = str(conn.get("ip_address", ""))
            if ip:
                all_ips.add(ip)

        if len(all_ips) <= 1:
            return True, 1.0

        # Получаем ASN для каждого IP
        ip_metadata = await self.geo_analyzer.geoip.lookup_batch(list(all_ips))

        asn_counts: Dict[Optional[int], int] = {}
        for ip, meta in ip_metadata.items():
            asn = meta.asn
            asn_counts[asn] = asn_counts.get(asn, 0) + 1

        if not asn_counts:
            return False, 0.0

        # Находим самый частый ASN
        max_asn_count = max(asn_counts.values())
        total_ips = len(ip_metadata)

        ratio = max_asn_count / total_ips if total_ips > 0 else 0.0

        # Считаем "один провайдер" если >= 70% IP от него
        is_same_asn = ratio >= 0.7

        return is_same_asn, ratio

    def _get_action(self, score: float) -> ViolationAction:
        """Определить рекомендуемое действие на основе скора."""
        if score < self.THRESHOLDS['no_action']:
            return ViolationAction.NO_ACTION
        elif score < self.THRESHOLDS['monitor']:
            return ViolationAction.MONITOR
        elif score < self.THRESHOLDS['warn']:
            return ViolationAction.WARN
        elif score < self.THRESHOLDS['soft_block']:
            return ViolationAction.SOFT_BLOCK
        elif score < self.THRESHOLDS['temp_block']:
            return ViolationAction.TEMP_BLOCK
        else:
            return ViolationAction.HARD_BLOCK
