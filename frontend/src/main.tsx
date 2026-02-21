import React, { useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import MainScreen from './components/ui/MainScreen';
import Tasks from './components/ui/Tasks';
import Pvp from './components/ui/Pvp';
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

/**
 * Если приложение открыто по invite-ссылке (start_param начинается с pvp_),
 * сразу перекидываем пользователя на /pvp, чтобы он видел дуэльный экран.
 */
function StartParamRedirect() {
  const navigate = useNavigate();

  useEffect(() => {
    try {
      const sp = (WebApp.initDataUnsafe as any)?.start_param;
      if (typeof sp === 'string' && sp.startsWith('pvp_')) {
        navigate('/pvp', { replace: true });
      }
    } catch {
      // ignore
    }
  }, [navigate]);

  return <MainScreen />;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        {/* вместо прямого MainScreen — ставим редирект-обертку */}
        <Route path="/" element={<StartParamRedirect />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/pvp" element={<Pvp />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);

