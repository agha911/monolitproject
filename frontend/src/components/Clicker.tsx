import React, { useState, useEffect } from 'react';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';
import MainButton from './MainButton';

const API_BASE_URL = 'https://monolitproject.onrender.com';

const telegramUser = WebApp.initDataUnsafe?.user;

if (!telegramUser) {
  alert("Ошибка: не удалось получить данные Telegram-пользователя.");
  throw new Error("Telegram user not found");
}

const telegramUserId = telegramUser.id;
const ENERGY_RESTORE_INTERVAL_MS = 1 * 60 * 1000; // 1 минута

const Clicker: React.FC = () => {
  const { t } = useTranslation();

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
    const initializeUser = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/game/progress/${telegramUserId}`);
        if (res.status === 404) {
          const regRes = await fetch(`${API_BASE_URL}/api/user/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              user_id: telegramUser.id,
              first_name: telegramUser.first_name,
              last_name: telegramUser.last_name,
              username: telegramUser.username,
            }),
          });
          if (!regRes.ok) throw new Error('Регистрация не удалась');
        }

        const finalRes = await fetch(`${API_BASE_URL}/api/game/progress/${telegramUserId}`);
        const data = await finalRes.json();
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
  }, []);

  useEffect(() => {
    const interval = setInterval(async () => {
      if (energy >= maxEnergy) return;

      try {
        const res = await fetch(`${API_BASE_URL}/api/game/progress/${telegramUserId}`);
        const data = await res.json();
        setEnergy(data.energy);
        setLastEnergyUpdate(data.lastEnergyUpdate ? new Date(data.lastEnergyUpdate) : null);
        setMaxEnergy(data.max_energy ?? 100);
      } catch (err) {
        console.error('Ошибка при автообновлении энергии:', err);
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [energy, maxEnergy]);

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
    if (loading || energy <= 0 || level >= 100) return;

    const newXp = xp + 1;
    const newTotalXp = totalXp + 1;
    const newEnergy = energy - 1;
    const newScore = score + 1;
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
      body: JSON.stringify({ user_id: telegramUserId }),
    });

    fetch(`${API_BASE_URL}/api/game/save_progress`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: telegramUserId,
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
      <h2 className="text-2xl font-bold mb-2 drop-shadow-md">💰 $MONO: {totalXp}</h2>
      <h3 className="text-lg font-medium mb-4">{t('level')}: {level} / 100</h3>

      <div className="my-4 w-full max-w-md">
        <label className="block mb-1 text-sm text-[#7ee9ff]">
          {t('xp')}: {xp} / {xpNeeded}
        </label>
        <div className="w-full h-4 bg-[#0d273d] rounded overflow-hidden shadow-inner">
          <div className="h-full bg-gradient-to-r from-[#00f0ff] to-[#00c2ff] transition-all" style={{ width: `${xpProgress}%` }} />
        </div>
      </div>

      <div className="my-4 w-full max-w-md">
        <label className="block mb-1 text-sm text-[#7ee9ff]">
          {t('energy')}: {energy} / {maxEnergy}
        </label>
        <div className="w-full h-4 bg-[#0d273d] rounded overflow-hidden shadow-inner">
          <div className="h-full bg-gradient-to-r from-[#7af9ff] to-[#00f0ff] transition-all" style={{ width: `${energyProgress}%` }} />
        </div>
        {energy < maxEnergy && timeToNextEnergy && (
          <p className="text-xs mt-1 text-[#89dfff]">
            +1 {t('energy')} {t('in')} {timeToNextEnergy}
          </p>
        )}
      </div>

      <div className="relative w-64 h-64 mt-6">
        <div className="absolute inset-0 flex items-center justify-center">
          <MainButton onHoldTick={handleClick} energy={energy} />
        </div>
        <div className="absolute top-0 left-0 w-8 h-8 rounded-full bg-[#00f0ff40] shadow-[0_0_10px_2px_#00f0ff]" />
        <div className="absolute top-0 right-0 w-8 h-8 rounded-full bg-[#00f0ff40] shadow-[0_0_10px_2px_#00f0ff]" />
        <div className="absolute bottom-0 left-0 w-8 h-8 rounded-full bg-[#00f0ff40] shadow-[0_0_10px_2px_#00f0ff]" />
        <div className="absolute bottom-0 right-0 w-8 h-8 rounded-full bg-[#00f0ff40] shadow-[0_0_10px_2px_#00f0ff]" />
      </div>
    </div>
  );
};

export default Clicker;







