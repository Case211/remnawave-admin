import type { DefaultTheme, LocaleSpecificConfig } from 'vitepress'

export const ru: LocaleSpecificConfig<DefaultTheme.Config> = {
  lang: 'ru-RU',
  description: 'Telegram-бот и веб-панель для управления Remnawave: анти-абуз, ноды, почта, мониторинг',
  themeConfig: {
    nav: [
      { text: 'Руководство', link: '/guide/overview', activeMatch: '/guide/' },
      { text: 'Справочник', link: '/reference/env', activeMatch: '/reference/' },
      { text: 'Релизы', link: '/releases/', activeMatch: '/releases/' },
      {
        text: 'Ссылки',
        items: [
          { text: 'Релизы на GitHub', link: 'https://github.com/Case211/remnawave-admin/releases' },
          { text: 'Обновления в Telegram', link: 'https://t.me/remnawave_admin/3032' },
          { text: 'Чат в Telegram', link: 'https://t.me/remnawave_admin' },
          { text: 'Issues', link: 'https://github.com/Case211/remnawave-admin/issues' },
        ],
      },
    ],

    sidebar: {
      '/guide/': [
        {
          text: 'Знакомство',
          items: [
            { text: 'Что это такое', link: '/guide/overview' },
            { text: 'Требования к серверу', link: '/guide/requirements' },
            { text: 'Установка', link: '/guide/installation' },
            { text: 'Обновление', link: '/guide/upgrade' },
          ],
        },
        {
          text: 'Настройка',
          items: [
            { text: 'Веб-панель и прокси', link: '/guide/web-panel' },
            { text: 'Доступ и роли', link: '/guide/access' },
            { text: 'Telegram-бот', link: '/guide/bot' },
            { text: 'Webhook от панели', link: '/guide/webhook-setup' },
          ],
        },
        {
          text: 'Ноды',
          items: [
            { text: 'Node Agent', link: '/guide/node-agent' },
            { text: 'Детект торрентов', link: '/guide/torrents' },
          ],
        },
        {
          text: 'Возможности',
          items: [
            { text: 'Анти-абуз', link: '/guide/anti-abuse' },
            { text: 'Отложенное применение мер', link: '/guide/enforcement-workflow' },
            { text: 'Почтовый сервер', link: '/guide/mail' },
            { text: 'Плагины', link: '/guide/plugins' },
            { text: 'Мониторинг', link: '/guide/monitoring' },
            { text: 'Бэкапы', link: '/guide/backups' },
          ],
        },
        {
          text: 'Эксплуатация',
          items: [
            { text: 'Решение проблем', link: '/guide/troubleshooting' },
            { text: 'Разработка', link: '/guide/development' },
            { text: 'Участие в проекте', link: '/guide/contributing' },
          ],
        },
      ],

      '/reference/': [
        {
          text: 'Справочник',
          items: [
            { text: 'Настройки панели', link: '/reference/settings' },
            { text: 'Переменные окружения', link: '/reference/env' },
            { text: 'Команды бота', link: '/reference/bot-commands' },
            { text: 'Структура проекта', link: '/reference/project-layout' },
          ],
        },
        {
          text: 'Внешний API',
          items: [
            { text: 'Обзор и ключи', link: '/reference/api' },
            { text: 'Эндпоинты', link: '/reference/api-endpoints' },
            { text: 'Ошибки', link: '/reference/api-errors' },
          ],
        },
        {
          text: 'Плагины',
          items: [
            { text: 'Разработка плагинов', link: '/reference/plugin-development' },
            { text: 'Plugin API', link: '/reference/plugin-api' },
          ],
        },
        {
          text: 'Исходящие webhook',
          items: [
            { text: 'Подписки и доставка', link: '/reference/webhooks' },
            { text: 'Каталог событий', link: '/reference/webhook-events' },
            { text: 'Проверка подписи', link: '/reference/webhook-signatures' },
          ],
        },
      ],

      '/releases/': [
        {
          text: 'Релизы',
          items: [
            { text: 'Все релизы', link: '/releases/' },
            { text: '5.0.0', link: '/releases/5.0.0' },
          ],
        },
      ],
    },

    editLink: {
      pattern: 'https://github.com/Case211/remnawave-admin/edit/main/docs/:path',
      text: 'Предложить правку',
    },
    lastUpdatedText: 'Обновлено',
    docFooter: { prev: 'Назад', next: 'Дальше' },
    outline: { label: 'На этой странице', level: [2, 3] },
    returnToTopLabel: 'Наверх',
    sidebarMenuLabel: 'Разделы',
    darkModeSwitchLabel: 'Тема',
    lightModeSwitchTitle: 'Светлая тема',
    darkModeSwitchTitle: 'Тёмная тема',
    langMenuLabel: 'Сменить язык',
    notFound: {
      title: 'Страница не найдена',
      quote: 'Такой страницы здесь нет — возможно, она переехала вместе с разделом.',
      linkText: 'На главную',
    },
    footer: {
      message: 'AGPL-3.0 с исключением для плагинов',
      copyright: 'Сделано для сообщества Remnawave',
    },
  },
}
