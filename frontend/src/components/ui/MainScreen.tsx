import React, { useState } from 'react';
import Clicker from '../Clicker';
import Tasks from './Tasks';
import Friends from './Friends';
import NavigationTabs from './NavigationTabs';
import Shop from './Shop';
// import Governance from './Governance'; // ⛔ временно отключили (можно включить обратно)
import Pvp from './Pvp'; // ✅ новая страница PvP
import LanguageSwitcher from './LanguageSwitcher';

type Tab = 'home' | 'tasks' | 'friends' | 'shop' | 'pvp'; 
// | 'governance'; // ⛔ вернуть обратно при необходимости

const MainScreen: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('home');

  return (
    <div className="pb-20 relative">
      <LanguageSwitcher />

      {activeTab === 'home' && <Clicker />}
      {activeTab === 'tasks' && <Tasks />}
      {activeTab === 'friends' && <Friends />}
      {activeTab === 'shop' && <Shop />}
      {activeTab === 'pvp' && <Pvp />}

      {/* {activeTab === 'governance' && <Governance />} */}{/* ⛔ отключено */}

      <NavigationTabs activeTab={activeTab} setActiveTab={setActiveTab} />
    </div>
  );
};

export default MainScreen;


