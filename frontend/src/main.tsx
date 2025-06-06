import React from 'react';
import ReactDOM from 'react-dom/client';
import MainScreen from './components/ui/MainScreen';
import './index.css';
import './i18n';
import WebApp from '@twa-dev/sdk';

WebApp.ready();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MainScreen />
  </React.StrictMode>
);
