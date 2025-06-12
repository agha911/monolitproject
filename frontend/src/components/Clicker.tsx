import React, { useState, useEffect } from 'react';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';
import MainButton from './MainButton';
import API_BASE_URL from './config';

const ENERGY_RESTORE_INTERVAL_MS = 1 * 60 * 1000;

const Clicker: React.FC = () => {
  const { t } = useTranslation();

  const [telegramUser, setTelegramUser] = useState<WebAppUser | null>(null);
  const [score, setScore] = useState(0);
  const [xp, setXp] = useState(0);
  const [totalXp, setTotalXp] = useState(0);
  const [level, setLevel] = useState(1);
  const [energy, setEnergy] = useState(100);
  const [maxEnergy, setMaxEnergy] = useState(100);
  const [lastEnergyUpdate, setLastEnergyUpdate] = useState<Date | null>(null);
  const [timeToNextEnergy, setTimeToNextEnergy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    WebApp.ready();
    const user = WebApp.initDataUnsafe?.user;
    if (user) {
      setTelegramUser(user);
    } else {
      alert('Ошибка: не удалось получить данные Telegram-пользователя.');
      console.warn('initDataUnsafe.user = ', WebApp.initDataUnsafe);
    }
  }, []);

  useEffect(() => {
    if (!telegramUser) return;

    const initializeUser = async () => {
      try {
        const registerUrl = `${API_BASE_URL}/api/user/register`;

        await fetch(registerUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initDataUnsafe }),
        });

        const res = await fetch(`${API_BASE_URL}/api/game/progress`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initDataUnsafe }),
        });

        const data = await res.json();
        setXp(data.xp);
        setLevel(data.level);
        setEnergy(data.energy);
        setTotalXp(data.total_xp ?? data.xp);
        setLastEnergyUpdate(data.lastEnergyUpdate ? new Date(data.lastEnergyUpdate) : null);
        setMaxEnergy(data.max_energy ?? 100);
        setLoading(false);
      } catch (error) {
        console.error('Ошибка инициализации пользователя:', error);
      }
    };

    initializeUser();
  }, [telegramUser]);



  useEffect(() => {
    const interval = setInterval(async () => {
      if (!telegramUser || energy >= maxEnergy) return;

      try {
        const res = await fetch(`${API_BASE_URL}/api/game/progress`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });
        const data = await res.json();
        setEnergy(data.energy);
        setLastEnergyUpdate(data.lastEnergyUpdate ? new Date(data.lastEnergyUpdate) : null);
        setMaxEnergy(data.max_energy ?? 100);
      } catch (err) {
        console.error('Ошибка при автообновлении энергии:', err);
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [telegramUser, energy, maxEnergy]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (!lastEnergyUpdate || energy >= maxEnergy) {
        setTimeToNextEnergy(null);
        return;
      }

      const now = new Date();
      const msPassed = now.getTime() - lastEnergyUpdate.getTime();
      const msToNext = ENERGY_RESTORE_INTERVAL_MS - (msPassed % ENERGY_RESTORE_INTERVAL_MS);
      const minutes = Math.floor(msToNext / 60000);
      const seconds = Math.floor((msToNext % 60000) / 1000);
      setTimeToNextEnergy(`${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`);
    }, 1000);

    return () => clearInterval(interval);
  }, [lastEnergyUpdate, energy, maxEnergy]);

  const handleClick = () => {
    if (!telegramUser || loading || energy <= 0 || level >= 100) return;

    const gain = 1;
    const newXp = xp + gain;
    const newTotalXp = totalXp + gain;
    const newEnergy = energy - 1;
    const newScore = score + gain;
    let newLevel = level;
    let adjustedXp = newXp;

    const xpNeeded = level * 100;
    if (newXp >= xpNeeded && level < 100) {
      newLevel = level + 1;
      adjustedXp = newXp - xpNeeded;
    }

    setScore(newScore);
    setXp(adjustedXp);
    setEnergy(newEnergy);
    setLevel(newLevel);
    setTotalXp(newTotalXp);

    fetch(`${API_BASE_URL}/api/game/click`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ init_data: WebApp.initData }),
    });

    fetch(`${API_BASE_URL}/api/game/save_progress`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        init_data: WebApp.initData,
        xp: adjustedXp,
        level: newLevel,
        energy: newEnergy,
        total_xp: newTotalXp,
      }),
    });
  };

  const xpNeeded = level * 100;
  const xpProgress = Math.min((xp / xpNeeded) * 100, 100);
  const energyProgress = Math.min((energy / maxEnergy) * 100, 100);

  return (
    <div className="w-full min-h-screen bg-[#131f2f] text-center flex flex-col items-center justify-start pt-8 px-4 text-[#00f0ff]">
      <h2 className="text-2xl font-bold mb-2 drop-shadow-md">$GAP: {totalXp}</h2>
      <h3 className="text-lg font-medium mb-4">{t('level')}: {level} / 100</h3>

      <div className="my-4 w-full max-w-md">
        <label className="block mb-1 text-sm text-[#7ee9ff]">{t('xp')}: {xp} / {xpNeeded}</label>
        <div className="w-full h-4 bg-[#0d273d] rounded overflow-hidden shadow-inner">
          <div className="h-full bg-gradient-to-r from-[#00f0ff] to-[#00c2ff] transition-all" style={{ width: `${xpProgress}%` }} />
        </div>
      </div>

      <div className="my-4 w-full max-w-md">
        <label className="block mb-1 text-sm text-[#7ee9ff]">{t('energy')}: {energy} / {maxEnergy}</label>
        <div className="w-full h-4 bg-[#0d273d] rounded overflow-hidden shadow-inner">
          <div className="h-full bg-gradient-to-r from-[#7af9ff] to-[#00f0ff] transition-all" style={{ width: `${energyProgress}%` }} />
        </div>
        {energy < maxEnergy && timeToNextEnergy && (
          <p className="text-xs mt-1 text-[#89dfff]">
            +1 {t('energy')} {t('in')} {timeToNextEnergy}
          </p>
        )}
      </div>

      <div className="relative w-96 h-96 mt-6">
        <div className="absolute inset-0 flex items-center justify-center">
          <MainButton onClick={handleClick} energy={energy} />
        </div>
      </div>
    </div>
  );
};

export default Clicker;















