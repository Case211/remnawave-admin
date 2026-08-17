import { defineConfig } from 'vitepress'
import { ru } from './locales/ru'
import { en } from './locales/en'

// Сайт живёт на GitHub Pages проекта, поэтому все ссылки идут от /remnawave-admin/.
// Русский — корневая локаль: основная аудитория читает по-русски.
export default defineConfig({
  base: '/remnawave-admin/',
  title: 'Remnawave Admin',
  lastUpdated: true,
  cleanUrls: true,
  ignoreDeadLinks: [
    // Ссылки на файлы репозитория, которых нет в сборке сайта.
    /^\.\.\//,
  ],

  // Аудиты и внутренние разборы лежат в репозитории, но страницами не становятся:
  // это рабочие документы, а не руководство для оператора.
  srcExclude: ['audits/**', 'README.md'],


  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/remnawave-admin/logo.svg' }],
    ['meta', { name: 'theme-color', content: '#4283f6' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:image', content: '/remnawave-admin/og-image.png' }],
  ],

  locales: {
    root: { label: 'Русский', ...ru },
    en: { label: 'English', ...en },
  },

  themeConfig: {
    logo: '/logo.svg',
    socialLinks: [
      { icon: 'github', link: 'https://github.com/Case211/remnawave-admin' },
      { icon: 'telegram', link: 'https://t.me/remnawave_admin' },
    ],
    search: {
      provider: 'local',
      options: {
        locales: {
          root: {
            translations: {
              button: { buttonText: 'Поиск', buttonAriaLabel: 'Поиск по документации' },
              modal: {
                displayDetails: 'Показать подробности',
                resetButtonTitle: 'Сбросить поиск',
                backButtonTitle: 'Закрыть поиск',
                noResultsText: 'Ничего не найдено',
                footer: {
                  selectText: 'выбрать',
                  navigateText: 'перейти',
                  closeText: 'закрыть',
                },
              },
            },
          },
        },
      },
    },
  },
})
