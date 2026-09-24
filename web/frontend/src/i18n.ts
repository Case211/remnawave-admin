import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import ru from './locales/ru/translation.json'
import en from './locales/en/translation.json'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      ru: { translation: ru },
      en: { translation: en },
    },
    fallbackLng: 'ru',
    interpolation: {
      // React сам экранирует текст при выводе; с escapeValue: true значения
      // экранировались дважды — «Europe/Moscow» показывалось как
      // «Europe&#x2F;Moscow», «A&B» как «A&amp;B». Сырого HTML из t() нет.
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'i18nextLng',
    },
  })

export default i18n
