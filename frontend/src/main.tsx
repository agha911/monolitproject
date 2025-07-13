import React from 'react';
import ReactDOM from 'react-dom/client';
import MainScreen from './components/ui/MainScreen';
import './index.css';
import './i18n';
import WebApp from '@twa-dev/sdk';
import Tournament from './components/ui/Tournament'; // 👈 новый импорт (если понадобится напрямую)

// Безопасная инициализация Telegram WebApp
if (typeof WebApp !== 'undefined' && WebApp.initDataUnsafe?.user) {
  WebApp.ready();
  console.log('[Telegram WebApp] Инициализирован для пользователя:', WebApp.initDataUnsafe.user);
} else {
  console.warn('[Telegram WebApp] Пользователь не определён — запуск вне Telegram?');
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MainScreen />
  </React.StrictMode>
);

