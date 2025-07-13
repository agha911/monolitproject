import React, { useState, useEffect } from 'react';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';
import MainButton from './MainButton';
import API_BASE_URL from './config';

const ENERGY_RESTORE_INTERVAL_MS = 1 * 60 * 1000;

interface FloatingText {
  id: number;
  value: number;
  x: number;
  y: number;
}

const Clicker: React.FC = () => {
  const { t } = useTranslation();

  const [telegramUser, setTelegramUser] = useState<WebAppUser | null>(null);
  const [score, setScore] = useState(0);
  const [totalXp, setTotalXp] = useState(0);
  const [energy, setEnergy] = useState(100);
  const [maxEnergy, setMaxEnergy] = useState(100);
  const [lastEnergyUpdate, setLastEnergyUpdate] = useState<Date | null>(null);
  const [timeToNextEnergy, setTimeToNextEnergy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [floatingTexts, setFloatingTexts] = useState<FloatingText[]>([]);
  const [clickBoost, setClickBoost] = useState(1);

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

  const fetchProgress = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/game/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: WebApp.initData }),
      });

      const data = await res.json();
      setEnergy(data.energy);
      setTotalXp(data.total_xp ?? 0);
      setLastEnergyUpdate(data.lastEnergyUpdate ? new Date(data.lastEnergyUpdate) : null);
      setMaxEnergy(data.max_energy ?? 100);
      setClickBoost((data.click_boost_level ?? 0) + 1);
      setLoading(false);
    } catch (err) {
      console.error('Ошибка получения прогресса:', err);
    }
  };

  useEffect(() => {
    if (telegramUser) fetchProgress();
  }, [telegramUser]);

  useEffect(() => {
    const tickEnergy = async () => {
      if (!lastEnergyUpdate || energy >= maxEnergy) return;

      const now = new Date();
      const minutesPassed = Math.floor((now.getTime() - lastEnergyUpdate.getTime()) / 60000);
      const energyToRestore = Math.floor(minutesPassed);

      if (energyToRestore > 0) {
        await fetchProgress(); // сервер сам обновит энергию по lastEnergyUpdate
      }
    };

    const interval = setInterval(() => {
      tickEnergy();

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

  const handleMultiClick = (x: number, y: number) => {
    if (!telegramUser || loading || energy <= 0) return;

    const gain = clickBoost;
    const newTotalXp = totalXp + gain;
    const newEnergy = energy - gain;
    const newScore = score + gain;

    setScore(newScore);
    setEnergy(newEnergy);
    setTotalXp(newTotalXp);

    const newId = Date.now() + Math.random();
    const newText: FloatingText = { id: newId, value: gain, x, y };
    setFloatingTexts((prev) => [...prev, newText]);
    setTimeout(() => {
      setFloatingTexts((prev) => prev.filter((t) => t.id !== newId));
    }, 1000);

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
        energy: newEnergy,
        total_xp: newTotalXp,
      }),
    });
  };

  const energyProgress = Math.min((energy / maxEnergy) * 100, 100);

  return (
    <div className="w-full min-h-screen bg-[#131f2f] text-center flex flex-col items-center justify-start pt-8 px-4 text-[#00f0ff]">
      <h2 className="text-2xl font-bold mb-2 drop-shadow-md">$GAP: {totalXp}</h2>
      <div className="text-sm text-[#7ee9ff] mb-2">x{clickBoost} boost</div>

      <div className="my-4 w-full max-w-md">
        <label className="block mb-1 text-sm text-[#7ee9ff]">
          {t('energy')}: {energy} / {maxEnergy}
        </label>
        <div className="w-full h-4 bg-[#0d273d] rounded overflow-hidden shadow-inner">
          <div
            className="h-full bg-gradient-to-r from-[#7af9ff] to-[#00f0ff] transition-all"
            style={{ width: `${energyProgress}%` }}
          />
        </div>
        {energy < maxEnergy && timeToNextEnergy && (
          <p className="text-xs mt-1 text-[#89dfff]">
            +1 {t('energy')} {t('in')} {timeToNextEnergy}
          </p>
        )}
      </div>

      <div className="relative w-96 h-96 mt-6">
        <div className="absolute inset-0 flex items-center justify-center">
          <MainButton energy={energy} onMultiClick={handleMultiClick} />
        </div>
        {floatingTexts.map((text) => (
          <div
            key={text.id}
            className="absolute text-lg font-bold text-yellow-300 animate-float"
            style={{ left: `${text.x}%`, top: `${text.y}%` }}
          >
            +{text.value}
          </div>
        ))}
      </div>
    </div>
  );
};

export default Clicker;




















