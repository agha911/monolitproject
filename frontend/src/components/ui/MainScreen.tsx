import React, { useState } from 'react';
import Clicker from '../Clicker';
import Tasks from './Tasks';
import Friends from './Friends';
import NavigationTabs from './NavigationTabs';
import Shop from './Shop';
// import Tournament from './Tournament'; // ❌ больше не используем
import Governance from './Governance';     // ✅ новая страница
import LanguageSwitcher from './LanguageSwitcher';

type Tab = 'home' | 'tasks' | 'friends' | 'shop' | 'governance';

const MainScreen: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('home');

  return (
    <div className="pb-20 relative">
      <LanguageSwitcher />

      {activeTab === 'home' && <Clicker />}
      {activeTab === 'tasks' && <Tasks />}
      {activeTab === 'friends' && <Friends />}
      {activeTab === 'shop' && <Shop />}
      {activeTab === 'governance' && <Governance />}{/* ✅ рендер новой страницы */}

      <NavigationTabs activeTab={activeTab} setActiveTab={setActiveTab} />
    </div>
  );
};

export default MainScreen;

