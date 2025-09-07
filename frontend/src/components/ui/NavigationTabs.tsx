import React from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  activeTab: 'home' | 'tasks' | 'friends' | 'shop' | 'tournament';
  setActiveTab: (tab: 'home' | 'tasks' | 'friends' | 'shop' | 'tournament') => void;
}

const NavigationTabs: React.FC<Props> = ({ activeTab, setActiveTab }) => {
  const { t } = useTranslation();

  const baseBtn =
    'flex flex-col items-center flex-1 py-1 transition-all duration-200 ease-out active:scale-95';
  const active =
    'text-[#7af9ff] font-bold drop-shadow-[0_0_6px_#00f0ff80]';
  const inactive =
    'text-[#00f0ff] opacity-80 hover:opacity-100 hover:drop-shadow-[0_0_4px_#00f0ff40]';

  return (
    <div className="fixed bottom-0 w-full flex justify-around bg-[#0e1a2b] border-t border-[#00f0ff40] py-2 shadow-[0_0_10px_#00f0ff20]">
      <button
        onClick={() => setActiveTab('home')}
        className={`${baseBtn} ${activeTab === 'home' ? active : inactive}`}
      >
        <span className="text-lg">🏠</span>
        <span className="text-[11px] mt-0.5">{t('tab_home')}</span>
      </button>

      <button
        onClick={() => setActiveTab('tasks')}
        className={`${baseBtn} ${activeTab === 'tasks' ? active : inactive}`}
      >
        <span className="text-lg">📋</span>
        <span className="text-[11px] mt-0.5">{t('tab_tasks')}</span>
      </button>

      <button
        onClick={() => setActiveTab('friends')}
        className={`${baseBtn} ${activeTab === 'friends' ? active : inactive}`}
      >
        <span className="text-lg">👥</span>
        <span className="text-[11px] mt-0.5">{t('tab_friends')}</span>
      </button>

      <button
        onClick={() => setActiveTab('shop')}
        className={`${baseBtn} ${activeTab === 'shop' ? active : inactive}`}
      >
        <span className="text-lg">🛒</span>
        <span className="text-[11px] mt-0.5">{t('tab_shop')}</span>
      </button>

      {/* Турнирная вкладка переиспользуется для Governance */}
      <button
        onClick={() => setActiveTab('tournament')}
        className={`${baseBtn} ${activeTab === 'tournament' ? active : inactive}`}
      >
        <span className="text-lg">⚖️</span>
        <span className="text-[11px] mt-0.5">{t('tab_governance')}</span>
      </button>
    </div>
  );
};

export default NavigationTabs;



