"""Auto-extracted from shared/violation_detector.py."""
import asyncio
import json
import re
import time
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as tz
from itertools import combinations
from math import radians, sin, cos, sqrt, atan2
from typing import List, Dict, Any, Optional, Set
from enum import Enum

from shared.analyzers.models import (
    ViolationAction, TemporalScore, GeoScore, ASNScore, ProfileScore,
    DeviceScore, HwidScore, UserAgentClassification, SuspiciousAgent,
    UserAgentScore, ViolationScore,
)
from shared.connection_monitor import ConnectionMonitor, ActiveConnection, ConnectionStats
from shared.logger import logger

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
        user_device_count: int = 1,
        is_mobile: bool = False,
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
        overlap_minutes = 0.0

        # Проверка одновременных подключений
        # Считаем уникальные IP и проверяем, действительно ли подключения одновременные
        # Подключения считаются одновременными только если они созданы в пределах окна
        # (2 минуты) - это учитывает нормальное переключение между сетями (Wi-Fi <-> мобильная)
        # Также учитываем роутинг в приложении - пользователь может периодически подключаться/отключаться
        if len(connections) > 1:
            from shared.config_service import config_service
            simultaneous_window_seconds = 120  # Окно для определения одновременности (2 минуты)
            max_connection_age_seconds = 600   # Подключения старше этого считаются устаревшими (10 минут)
            sequential_switch_threshold = 300  # Разрыв между подключениями, указывающий на переключение (5 минут)
            max_connection_age_hours = 24  # Максимальный возраст подключения для учёта
            # Учитываем количество устройств пользователя - если у пользователя несколько устройств,
            # то несколько одновременных подключений могут быть нормальными
            try:
                config_max_ips = config_service.get("violations_max_simultaneous_ips", 0)
                max_allowed_simultaneous = config_max_ips if config_max_ips > 0 else max(1, user_device_count)
            except Exception as e:
                logger.debug("Failed to get config for violations_max_simultaneous_ips: %s, using default", e)
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

                # Нормализуем timezone в UTC перед сравнением
                if conn_time.tzinfo:
                    conn_time = conn_time.astimezone(tz.utc).replace(tzinfo=None)

                # Пропускаем слишком старые подключения (старше 24 часов)
                age_hours = (now - conn_time).total_seconds() / 3600
                if age_hours > max_connection_age_hours:
                    continue

                # Пропускаем подключения, которые были неактивны слишком долго
                # Это устаревшие (зависшие) подключения или переподключения через роутинг
                # Не считаем их одновременными
                age_seconds = (now - conn_time).total_seconds()
                if age_seconds > max_connection_age_seconds:
                    continue

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
                    
                    # Если разрыв больше порога переключения (5 минут), это последовательное переподключение
                    # Не считаем это одновременным подключением
                    if time_diff_seconds > sequential_switch_threshold:
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
                    # - Буфер для переключения сетей (WiFi <-> Mobile, роутинг, погрешности disconnect)
                    # - Превышение буфера = нарушение
                    #
                    # Буфер зависит от количества устройств:
                    # - 1-2 устройства: буфер +1 (переключение WiFi <-> Mobile)
                    # - 3+ устройств: буфер +2 (несколько устройств могут одновременно переключать сети)
                    if user_device_count <= 2:
                        network_switch_buffer = 1
                    else:
                        network_switch_buffer = 2

                    # CGNAT: мобильные операторы дают 3-5 IP с одного устройства
                    cgnat_buffer = 0
                    if is_mobile:
                        try:
                            cgnat_buffer = int(config_service.get("violations_mobile_cgnat_buffer", 3))
                        except Exception as e:
                            logger.debug("Failed to get config for violations_mobile_cgnat_buffer: %s, using default", e)
                            cgnat_buffer = 3

                    effective_threshold = max_allowed_simultaneous + network_switch_buffer + cgnat_buffer

                    if user_device_count >= 3:
                        effective_threshold += 1

                    # Проверяем превышение с учётом буфера
                    if simultaneous_count > effective_threshold:
                        # Превышение буфера — вероятно шаринг
                        excess = simultaneous_count - effective_threshold
                        if excess >= 3 or simultaneous_count > 10:
                            # Сильное превышение
                            score = 100.0
                            reasons.append(f"Множественные одновременные подключения с {simultaneous_count} разных IP (превышение на {excess}, порог: {effective_threshold}, устройств: {user_device_count})")
                        elif excess >= 2:
                            # Умеренное превышение
                            score = 80.0
                            reasons.append(f"Одновременные подключения с {simultaneous_count} разных IP (превышение на {excess}, порог: {effective_threshold}, устройств: {user_device_count})")
                        else:
                            # Превышение на 1 сверх буфера
                            score = 60.0
                            reasons.append(f"Превышение лимита устройств: {simultaneous_count} IP (порог: {effective_threshold}, устройств: {user_device_count})")
                    elif simultaneous_count > max_allowed_simultaneous:
                        # IP > устройств, но в пределах буфера — скорее всего переключение сети
                        # Минимальный скор для мониторинга, не классифицируем как нарушение
                        excess_over_limit = simultaneous_count - max_allowed_simultaneous
                        if excess_over_limit >= 2:
                            score = 35.0
                            reasons.append(f"Подозрительная активность: {simultaneous_count} IP при лимите {max_allowed_simultaneous} устройств")
                        else:
                            score = 15.0
                            reasons.append(f"Возможное переключение сети: {simultaneous_count} IP при лимите {max_allowed_simultaneous} устройств")

                    # Анализ длительности перекрытия сессий
                    # Кратковременное перекрытие (< 3 мин) — почти наверняка переключение сети
                    # Длительное перекрытие (> 15 мин) — подозрительно
                    if simultaneous_groups and score > 0:
                        best_group = max(simultaneous_groups, key=lambda g: len(set(ip for _, ip in g)))
                        # Длительность перекрытия = разница между самым ранним и самым поздним подключением в группе
                        earliest_start = min(t for t, _ in best_group)
                        latest_start = max(t for t, _ in best_group)
                        # Реальное перекрытие: от последнего подключения до текущего момента
                        # (все подключения в группе активны одновременно с момента latest_start)
                        overlap_minutes = (now - latest_start).total_seconds() / 60
                        # Но также учитываем разброс: если все подключились в одну секунду — это подозрительнее
                        group_spread_minutes = (latest_start - earliest_start).total_seconds() / 60

                        # M2: при ЯВНОМ массовом шаринге (сильное превышение лимита устройств)
                        # overlap-dampening НЕ применяем — это не «переключение сети». Иначе из-за
                        # max_age 10мин потолок score держался на 70 и temporal-floor (>=80) был мёртв.
                        # Мобильных это не задевает: их гасит CGNAT-буфер (выше порог) + floor_suppressed.
                        strong_sharing = simultaneous_count > 5 or (simultaneous_count - effective_threshold) >= 3
                        if strong_sharing:
                            pass  # реальный массовый шаринг — score не снижаем
                        elif overlap_minutes < 2:
                            # Очень короткое перекрытие — переключение сети, сильно снижаем
                            score *= 0.15
                            reasons.append(f"Кратковременное перекрытие ({overlap_minutes:.1f} мин) — вероятно переключение сети")
                        elif overlap_minutes < 5:
                            # Короткое перекрытие — возможно переключение
                            score *= 0.4
                        elif overlap_minutes < 15:
                            # Среднее перекрытие — неоднозначно
                            score *= 0.7
                        # > 15 мин — длительное перекрытие, скор не снижаем

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
                    # Нормализуем timezone — приводим к naive UTC для корректного сравнения
                    if curr_time.tzinfo:
                        curr_time_with_tz = curr_time.astimezone(tz.utc).replace(tzinfo=None)
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
            rapid_switches_count=rapid_switches,
            overlap_duration_minutes=overlap_minutes
        )


