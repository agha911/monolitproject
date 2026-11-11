import './apiFetch';
import Demo from './Demo';
import DemoNotice from './DemoNotice';
import { initializeDemo, isDemo } from './telegram';
import React, { useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import MainScreen from './components/ui/MainScreen';
import Tasks from './components/ui/Tasks';
import Pvp from './components/ui/Pvp';
import './index.css';
import './i18n';
import WebApp from './telegram';

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
      const sp = WebApp.initDataUnsafe?.start_param;
      if (typeof sp === 'string' && sp.startsWith('pvp_')) {
        navigate('/pvp', { replace: true });
      }
    } catch {
      // ignore
    }
  }, [navigate]);

  return <MainScreen />;
}

const root = ReactDOM.createRoot(document.getElementById('root')!);
async function start() {
  try {
    await initializeDemo();
  } catch (error) {
    root.render(<div className="demo-start-error"><h1>Monolit demo</h1><p>{error instanceof Error ? error.message : 'Unable to start demo.'}</p><button onClick={() => window.location.reload()}>Retry</button></div>);
    return;
  }
  root.render(
  <React.StrictMode>
    {isDemo && <DemoNotice />}
    <div className={isDemo ? 'demo-original' : undefined}>
    <BrowserRouter>
      <Routes>
        {/* вместо прямого MainScreen — ставим редирект-обертку */}
        <Route path="/" element={<StartParamRedirect />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/pvp" element={<Pvp />} />
        {isDemo && <Route path="/playground" element={<Demo />} />}
      </Routes>
    </BrowserRouter>
    </div>
  </React.StrictMode>
);
}
void start();

