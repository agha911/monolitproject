import React from 'react';
import { useTranslation } from 'react-i18next';

const LanguageSwitcher: React.FC = () => {
  const { i18n } = useTranslation();

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
    localStorage.setItem('lang', lng); // ✅ сохраняем выбор
  };

  return (
    <div className="fixed top-2 right-2 z-50 flex gap-2 text-sm text-[#00f0ff]">
      <button onClick={() => changeLanguage('en')} className="hover:underline">🇬🇧</button>
      <button onClick={() => changeLanguage('ru')} className="hover:underline">🇷🇺</button>
      <button onClick={() => changeLanguage('az')} className="hover:underline">🇦🇿</button>
    </div>
  );
};

export default LanguageSwitcher;
