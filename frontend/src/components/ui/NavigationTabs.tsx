import React from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  activeTab: 'home' | 'tasks' | 'friends' | 'shop';
  setActiveTab: (tab: 'home' | 'tasks' | 'friends' | 'shop') => void;
}

const NavigationTabs: React.FC<Props> = ({ activeTab, setActiveTab }) => {
  const { t } = useTranslation();

  return (
    <div className="fixed bottom-0 w-full flex justify-around bg-[#0e1a2b] border-t border-[#00f0ff40] py-2 text-[#00f0ff] shadow-[0_0_10px_#00f0ff20]">
      <button
        onClick={() => setActiveTab('home')}
        className={`flex flex-col items-center ${activeTab === 'home' ? 'font-bold text-[#7af9ff]' : ''}`}
      >
        🏠
        <span className="text-xs">{t('tab_home')}</span>
      </button>
      <button
        onClick={() => setActiveTab('tasks')}
        className={`flex flex-col items-center ${activeTab === 'tasks' ? 'font-bold text-[#7af9ff]' : ''}`}
      >
        📋
        <span className="text-xs">{t('tab_tasks')}</span>
      </button>
      <button
        onClick={() => setActiveTab('friends')}
        className={`flex flex-col items-center ${activeTab === 'friends' ? 'font-bold text-[#7af9ff]' : ''}`}
      >
        👥
        <span className="text-xs">{t('tab_friends')}</span>
      </button>
      <button
        onClick={() => setActiveTab('shop')}
        className={`flex flex-col items-center ${activeTab === 'shop' ? 'font-bold text-[#7af9ff]' : ''}`}
      >
        🛒
        <span className="text-xs">{t('tab_shop')}</span>
      </button>
    </div>
  );
};

export default NavigationTabs;


