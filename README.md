<div align="center">

<img src="remnawave-admin.webp" alt="Remnawave Admin" width="100%" />

# Remnawave Admin

**Панель управления и Telegram-бот поверх вашей панели Remnawave**

Пользователи, ноды, анти-абуз, почта и мониторинг — в одном месте

[![Stars](https://img.shields.io/github/stars/Case211/remnawave-admin?style=flat-square&logo=github&logoColor=white&labelColor=1f2430&color=f5c518)](https://github.com/Case211/remnawave-admin/stargazers) [![Release](https://img.shields.io/github/v/release/Case211/remnawave-admin?style=flat-square&logo=github&logoColor=white&labelColor=1f2430&color=3fb950)](https://github.com/Case211/remnawave-admin/releases/latest) [![Last commit](https://img.shields.io/github/last-commit/Case211/remnawave-admin/main?style=flat-square&logo=git&logoColor=white&labelColor=1f2430&color=8957e5)](https://github.com/Case211/remnawave-admin/commits/main) [![License](https://img.shields.io/badge/License-AGPL_v3-blue?style=flat-square&logo=gnu&logoColor=white)](LICENSE)

[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/) [![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/) [![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=white)](https://react.dev/) [![Prometheus](https://img.shields.io/badge/Prometheus-ready-E6522C?style=flat-square&logo=prometheus&logoColor=white)](https://case211.github.io/remnawave-admin/guide/monitoring)

### [📖 Документация](https://case211.github.io/remnawave-admin/) · [🚀 Установка](https://case211.github.io/remnawave-admin/guide/installation) · [💬 Чат](https://t.me/remnawave_admin)

[English](README_EN.md) · Русский

</div>

---

Панель Remnawave отвечает за пользователей и конфигурацию. Remnawave Admin берёт на себя всё остальное: собирает подключения с нод, ищет разделение подписок, шлёт уведомления, хранит историю и показывает, что происходит.

Работает поверх вашей панели по API, данные держит в своей базе. Ставится одной командой, всё лишнее выключается.

## Возможности

🛡 **Анти-абуз.** Семь анализаторов ищут разделение подписки: одновременные подключения, «невозможные путешествия», ASN, поведение, устройства, HWID, User-Agent. Считает источники, а не адреса, — мобильный CGNAT не превращается в компанию из четырёх человек. [Подробнее](https://case211.github.io/remnawave-admin/guide/anti-abuse)

🧲 **Детект торрентов.** Тег роутинга Xray плюс разбор трафика через nDPI: шифрованный BitTorrent, DHT и uTP тоже видно. Включается тумблером, демон едет внутри агента. [Подробнее](https://case211.github.io/remnawave-admin/guide/torrents)

🛰 **Агент на нодах.** Читает логи Xray, снимает метрики хоста, даёт удалённый терминал и каталог скриптов. Ставится одной строкой прямо из панели. [Подробнее](https://case211.github.io/remnawave-admin/guide/node-agent)

📧 **Почтовый сервер.** Прямая MX-доставка, DKIM, приём входящих, проверка SPF/DKIM/DMARC и разбор DMARC-отчётов — без внешних SMTP-провайдеров. [Подробнее](https://case211.github.io/remnawave-admin/guide/mail)

📈 **Мониторинг.** Метрики Prometheus из коробки, 30+ собственных показателей и пять готовых дашбордов Grafana. [Подробнее](https://case211.github.io/remnawave-admin/guide/monitoring)

🤖 **Telegram-бот.** Управление из чата, уведомления с кнопками действий, раскладка по топикам форума. [Подробнее](https://case211.github.io/remnawave-admin/guide/bot)

🔌 **Плагины и API.** Магазин плагинов внутри панели, свой API v3 с ключами и правами, исходящие webhook с подписью. [Подробнее](https://case211.github.io/remnawave-admin/guide/plugins)

📱 **Приложение для Android.** Виджет на главный экран, push-уведомления, несколько профилей панели.

А также: гео-карта подключений, аналитика с минутной грануляцией, конструктор автоматизаций, бэкапы по расписанию, аудит-лог, RBAC с ролями и правами, 2FA и биометрия, семь тем оформления, полный перевод на русский и английский.

## Установка

```bash
git clone https://github.com/Case211/remnawave-admin.git
cd remnawave-admin
cp .env.example .env
nano .env                          # токен бота, API панели, ваш Telegram ID

docker network create remnawave-network
docker compose up -d
```

Дальше — [reverse proxy и домен](https://case211.github.io/remnawave-admin/guide/web-panel), затем [агент на ноды](https://case211.github.io/remnawave-admin/guide/node-agent).

Полное руководство: **[case211.github.io/remnawave-admin](https://case211.github.io/remnawave-admin/guide/installation)**

## Требования

| | До 1 000 юзеров | 1 000–5 000 | 5 000–20 000 | 20 000+ |
|---|---|---|---|---|
| CPU | 2 vCPU | 4 vCPU | 8 vCPU | 8–16 vCPU |
| RAM | 4 GB | 8 GB | 16+ GB | 32+ GB |
| Диск | 40 GB SSD | 80 GB SSD | 240 GB NVMe | 240+ GB NVMe |

Плюс Docker, панель Remnawave с доступом к API и Telegram-бот. Образы собираются под `amd64` и `arm64`.

## Документация

| Раздел | О чём |
|--------|-------|
| [Установка](https://case211.github.io/remnawave-admin/guide/installation) | с нуля до работающей панели |
| [Переменные окружения](https://case211.github.io/remnawave-admin/reference/env) | полный справочник |
| [Веб-панель и прокси](https://case211.github.io/remnawave-admin/guide/web-panel) | Caddy, nginx, WebSocket, split-режим |
| [Анти-абуз](https://case211.github.io/remnawave-admin/guide/anti-abuse) | анализаторы, пороги, разбор инцидентов |
| [Внешний API](https://case211.github.io/remnawave-admin/reference/api) | ключи, области доступа, эндпоинты |
| [Webhook](https://case211.github.io/remnawave-admin/reference/webhooks) | события, подписи, повторы |
| [Решение проблем](https://case211.github.io/remnawave-admin/guide/troubleshooting) | что делать, когда не работает |

## Участие

Ошибки и предложения — в [issues](https://github.com/Case211/remnawave-admin/issues). Pull request приветствуются; при первом бот попросит подписать [CLA](CLA.md). Подробности — в [руководстве](https://case211.github.io/remnawave-admin/guide/contributing).

## Лицензия

GNU AGPL v3.0 с исключением для плагинов (§7) — см. [LICENSE](LICENSE). Версии до 2.15.x включительно остаются под MIT. Коммерческая лицензия — по запросу.

## Поддержать

TON `UQDDe-jyFTbQsPHqyojdFeO1_m7uPF-q1w0g_MfbSOd3l1sC`
USDT TRC20 `TGyHJj2PsYSUwkBbWdc7BFfsAxsE6SGGJP`
BTC `1J6Zz7XcrpFkchwFmuU5WTFYTxziBdSwRz`

<div align="center">

<a href="https://github.com/Case211/remnawave-admin/stargazers">
  <img src="docs/star-history.svg" alt="История звёзд" width="640" />
</a>

Сделано для сообщества Remnawave

</div>
