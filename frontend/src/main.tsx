import React from 'react';
import ReactDOM from 'react-dom/client';
import MainScreen from './components/ui/MainScreen';
import './index.css';
import './i18n';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MainScreen />
  </React.StrictMode>
);
