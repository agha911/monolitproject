import React, { useState } from 'react';
import Clicker from '../Clicker';
import Tasks from './Tasks';
import Friends from './Friends';
import NavigationTabs from './NavigationTabs';
import Shop from './Shop';
import Tournament from './Tournament'; // ✅ импорт турнира
import LanguageSwitcher from './LanguageSwitcher';

const MainScreen: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'home' | 'tasks' | 'friends' | 'shop' | 'tournament'>('home');

  return (
    <div className="pb-20 relative">
      <LanguageSwitcher />

      {activeTab === 'home' && <Clicker />}
      {activeTab === 'tasks' && <Tasks />}
      {activeTab === 'friends' && <Friends />}
      {activeTab === 'shop' && <Shop />}
      {activeTab === 'tournament' && <Tournament />} {/* ✅ новый экран */}

      <NavigationTabs activeTab={activeTab} setActiveTab={setActiveTab} />
    </div>
  );
};

export default MainScreen;

