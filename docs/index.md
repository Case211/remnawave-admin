---
layout: home

hero:
  name: Remnawave Admin
  text: Панель управления и Telegram-бот
  tagline: Пользователи, ноды, анти-абуз, почта и мониторинг — в одном месте, поверх вашей панели Remnawave
  image:
    src: /banner.webp
    alt: Remnawave Admin
  actions:
    - theme: brand
      text: Установить за 10 минут
      link: /guide/installation
    - theme: alt
      text: Что это такое
      link: /guide/overview
    - theme: alt
      text: GitHub
      link: https://github.com/Case211/remnawave-admin

features:
  - icon: 🛡
    title: Анти-абуз, который считает людей, а не адреса
    details: Семь анализаторов, от «невозможных путешествий» до общих HWID. Мобильный CGNAT не превращается в компанию из четырёх человек, а хостинг остаётся под подозрением.
    link: /guide/anti-abuse
    linkText: Как это устроено
  - icon: 🛰
    title: Агент на нодах
    details: Читает логи Xray, собирает метрики хоста, выполняет команды и скрипты. Ставится одной строкой прямо из панели.
    link: /guide/node-agent
    linkText: Установка агента
  - icon: 🧲
    title: Детект торрентов двумя способами
    details: Тег роутинга Xray плюс разбор трафика через nDPI — шифрованный BitTorrent, DHT и uTP тоже видно. Включается тумблером.
    link: /guide/torrents
    linkText: Включить
  - icon: 📧
    title: Свой почтовый сервер
    details: Прямая MX-доставка, DKIM, приём входящих, проверка SPF/DKIM/DMARC и разбор DMARC-отчётов. Без внешних SMTP-провайдеров.
    link: /guide/mail
    linkText: Настроить почту
  - icon: 📈
    title: Метрики и дашборды
    details: Эндпоинт /metrics в формате Prometheus, 30+ собственных метрик и пять готовых дашбордов Grafana.
    link: /guide/monitoring
    linkText: Подключить мониторинг
  - icon: 🔌
    title: Плагины и внешний API
    details: Магазин плагинов прямо в панели, собственный API v3 с ключами и правами, исходящие webhook с подписью.
    link: /guide/plugins
    linkText: Про плагины
---
