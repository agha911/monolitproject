import React, { useState, useEffect } from 'react';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';
import MainButton from './MainButton';
import API_BASE_URL from './config';



interface FloatingText {
  id: number;
  value: number;
  x: number;
  y: number;
}

const Clicker: React.FC = () => {
  const { t } = useTranslation();

  const [telegramUser, setTelegramUser] = useState<WebAppUser | null>(null);
  const [totalXp, setTotalXp] = useState(0);
  const [energy, setEnergy] = useState(100);
  const [maxEnergy, setMaxEnergy] = useState(100);
  const [lastEnergyUpdate, setLastEnergyUpdate] = useState<Date | null>(null);
  const [timeToNextEnergy, setTimeToNextEnergy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [clickBoost, setClickBoost] = useState(1);
  const [floatingTexts, setFloatingTexts] = useState<FloatingText[]>([]);

  useEffect(() => {
    WebApp.ready();
    const user = WebApp.initDataUnsafe?.user;
    if (user) {
      setTelegramUser(user);
    } else {
      alert('Ошибка: не удалось получить данные Telegram-пользователя.');
    }
  }, []);

  useEffect(() => {
    if (!telegramUser) return;

    const initializeUser = async () => {
      try {
        await fetch(`${API_BASE_URL}/api/user/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });

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
        setClickBoost((data.click_boost_level ?? 0) + 1);
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

      const totalRecoveryMinutes = 480; // 8 часов
      const recoveryIntervalMs = (totalRecoveryMinutes / maxEnergy) * 60 * 1000;

      const msToNext = recoveryIntervalMs - (msPassed % recoveryIntervalMs);
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

    setTotalXp(newTotalXp);
    setEnergy(newEnergy);

    const id = Date.now() + Math.random();
    setFloatingTexts((prev) => [...prev, { id, value: gain, x, y }]);
    setTimeout(() => {
      setFloatingTexts((prev) => prev.filter((t) => t.id !== id));
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
        total_xp: newTotalXp,
        energy: newEnergy,
      }),
    });
  };

  const energyProgress = Math.min((energy / maxEnergy) * 100, 100);

  return (
    <div className="w-full min-h-screen bg-[#131f2f] text-center flex flex-col items-center justify-start pt-8 px-4 text-[#00f0ff]">
      <h2 className="text-2xl font-bold mb-2 drop-shadow-md">$GAP: {totalXp}</h2>
      <div className="text-sm text-[#7ee9ff] mb-2">x{clickBoost} boost</div>

      <div className="my-4 w-full max-w-md">
        <label className="block mb-1 text-sm text-[#7ee9ff]">{t('energy')}: {energy} / {maxEnergy}</label>
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
            className="absolute text-lg font-bold text-yellow-300"
            style={{
              left: `${text.x}%`,
              top: `${text.y}%`,
              transform: 'translate(-50%, -50%)',
              pointerEvents: 'none',
              animation: 'floatUpFade 1s ease-out',
            }}
          >
            +{text.value}
          </div>
        ))}

        <style>{`
          @keyframes floatUpFade {
            0% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
            100% { opacity: 0; transform: translate(-50%, -100%) scale(1.2); }
          }
        `}</style>
      </div>
    </div>
  );
};

export default Clicker;










































































