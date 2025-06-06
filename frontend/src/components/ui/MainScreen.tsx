import React, { useState } from 'react';
import Clicker from '../Clicker';
import Tasks from './Tasks';
import Friends from './Friends';
import NavigationTabs from './NavigationTabs';
import Shop from './Shop';
import LanguageSwitcher from './LanguageSwitcher'; // ✅ импорт переключателя

const MainScreen: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'home' | 'tasks' | 'friends' | 'shop'>('home');

  return (
    <div className="pb-20 relative">
      <LanguageSwitcher /> {/* ✅ компонент переключателя языков */}

      {activeTab === 'home' && <Clicker />}
      {activeTab === 'tasks' && <Tasks />}
      {activeTab === 'friends' && <Friends />}
      {activeTab === 'shop' && <Shop />}

      <NavigationTabs activeTab={activeTab} setActiveTab={setActiveTab} />
    </div>
  );
};

export default MainScreen;
