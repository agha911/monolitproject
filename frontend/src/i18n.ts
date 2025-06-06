import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from './locales/en.json';
import ru from './locales/ru.json';
import az from './locales/az.json';

const savedLanguage = localStorage.getItem('lang');
const fallbackLang = savedLanguage || (window?.Telegram?.WebApp?.initDataUnsafe?.user?.language_code?.split('-')[0]) || 'en';

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      ru: { translation: ru },
      az: { translation: az },
    },
    lng: fallbackLang,
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false,
    },
  });

export default i18n;