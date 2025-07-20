import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import MainScreen from './components/ui/MainScreen';
import Tasks from './components/ui/Tasks';
import './index.css';
import './i18n';
import WebApp from '@twa-dev/sdk';

// Безопасная инициализация Telegram WebApp
if (typeof WebApp !== 'undefined' && WebApp.initDataUnsafe?.user) {
  WebApp.ready();
  console.log('[Telegram WebApp] Инициализирован для пользователя:', WebApp.initDataUnsafe.user);
} else {
  console.warn('[Telegram WebApp] Пользователь не определён — запуск вне Telegram?');
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainScreen />} />
        <Route path="/tasks" element={<Tasks />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);

