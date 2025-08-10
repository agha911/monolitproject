import React, { useState, useEffect, useMemo } from 'react';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';
import MainButton from './MainButton';
import API_BASE_URL from './config';
import { useClickBuffer, FlushResponse } from '../hooks/useClickBuffer';

interface FloatingText {
  id: number;
  value: number;
  x: number;
  y: number;
}

type WebAppUser = any;

const Clicker: React.FC = () => {
  const { t } = useTranslation();

  const [telegramUser, setTelegramUser] = useState<WebAppUser | null>(null);
  const [totalXp, setTotalXp] = useState(0);
  const [energy, setEnergy] = useState(1000);
  const [maxEnergy, setMaxEnergy] = useState(1000);
  const [lastEnergyUpdate, setLastEnergyUpdate] = useState<Date | null>(null);
  const [timeToFullEnergy, setTimeToFullEnergy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [clickBoost, setClickBoost] = useState(1);
  const [floatingTexts, setFloatingTexts] = useState<FloatingText[]>([]);
  const [serverSeq, setServerSeq] = useState<number | null>(null);
  const [seqReady, setSeqReady] = useState(false);

  useEffect(() => {
    WebApp.ready();
    const user = WebApp.initDataUnsafe?.user;
    if (user) setTelegramUser(user);
    else alert('Ошибка: не удалось получить данные Telegram-пользователя.');
  }, []);

  const userId = telegramUser?.id ? String(telegramUser.id) : 'guest';
  const sessionId = useMemo(() => `${userId}-${Date.now()}`, [userId]);
  const seqStorageKey = useMemo(() => `gappick:lastSeq:${userId}`, [userId]);

  const initialLocalSeq = useMemo(() => {
    try {
      const saved = localStorage.getItem(seqStorageKey);
      return saved ? Number(saved) : 0;
    } catch {
      return 0;
    }
  }, [seqStorageKey]);

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
        setMaxEnergy(data.max_energy ?? 1000);
        setClickBoost((data.click_boost_level ?? 0) + 1);

        const s = Number(data.last_client_seq ?? 0);
        setServerSeq(s);
        try { localStorage.setItem(seqStorageKey, String(s)); } catch {}

        setSeqReady(true);
        setLoading(false);
      } catch (error) {
        console.error('Ошибка инициализации пользователя:', error);
        setSeqReady(false);
      }
    };

    initializeUser();
  }, [telegramUser, seqStorageKey]);

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
        setMaxEnergy(data.max_energy ?? 1000);
        setClickBoost((data.click_boost_level ?? 0) + 1);

        const s = Number(data.last_client_seq ?? 0);
        if (serverSeq === null || s > serverSeq) {
          setServerSeq(s);
          try { localStorage.setItem(seqStorageKey, String(s)); } catch {}
          setSeqReady(true);
        }
      } catch (err) {
        console.error('Ошибка при автообновлении энергии:', err);
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [telegramUser, energy, maxEnergy, serverSeq, seqStorageKey]);

  // таймер до полного восстановления
  useEffect(() => {
    const interval = setInterval(() => {
      if (!lastEnergyUpdate || energy >= maxEnergy) {
        setTimeToFullEnergy(null);
        return;
      }
      const now = new Date();
      const msPassed = now.getTime() - lastEnergyUpdate.getTime();
      const totalRecoveryMinutes = 480;
      const intervalMsPerUnit = (totalRecoveryMinutes / maxEnergy) * 60 * 1000;
      const remainingUnits = maxEnergy - energy;
      const msToNextUnit = intervalMsPerUnit - (msPassed % intervalMsPerUnit);
      const msToFull = (remainingUnits - 1) * intervalMsPerUnit + msToNextUnit;
      const totalSeconds = Math.max(0, Math.ceil(msToFull / 1000));
      const hours = Math.floor(totalSeconds / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = totalSeconds % 60;
      const hh = hours.toString().padStart(2, '0');
      const mm = minutes.toString().padStart(2, '0');
      const ss = seconds.toString().padStart(2, '0');
      setTimeToFullEnergy(`${hh}:${mm}:${ss}`);
    }, 1000);

    return () => clearInterval(interval);
  }, [lastEnergyUpdate, energy, maxEnergy]);

  const onReconcile = async (data: FlushResponse) => {
    // всегда подтягиваем авторитетные значения
    setEnergy(data.energy);
    setTotalXp(data.total_xp);

    const s = Number(data.server_seq ?? 0);
    if (!Number.isNaN(s) && s >= 0) {
      setServerSeq(s);
      try { localStorage.setItem(seqStorageKey, String(s)); } catch {}
    }

    if (data.status !== 'ok') {
      try {
        const res = await fetch(`${API_BASE_URL}/api/game/progress`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });
        const p = await res.json();
        setEnergy(p.energy);
        setTotalXp(p.total_xp ?? 0);
        setLastEnergyUpdate(p.lastEnergyUpdate ? new Date(p.lastEnergyUpdate) : null);
        setMaxEnergy(p.max_energy ?? 1000);
        setClickBoost((p.click_boost_level ?? 0) + 1);
        const ps = Number(p.last_client_seq ?? 0);
        setServerSeq(ps);
        try { localStorage.setItem(seqStorageKey, String(ps)); } catch {}
        setSeqReady(true);
      } catch (e) {
        console.warn('refresh after noop failed', e);
      }
    }
  };

  const { addClicks /*, forceFlush*/ } = useClickBuffer({
    initData: WebApp.initData,
    sessionId,
    onReconcile,
    enabled: seqReady && !!telegramUser,
    flushEveryMs: 200,
    threshold: 50,
    initialSeq: Math.max(serverSeq ?? 0, initialLocalSeq),
    maxBatch: 50,
  });

  const handleMultiClick = (x: number, y: number) => {
    if (!telegramUser || loading || energy <= 0) return;

    // одна «сырая» единица = 1 очко, но кликаем по boost-значению
    const spend = Math.min(clickBoost, energy);
    if (spend <= 0) return;

    // локальный UI
    setTotalXp((prev) => prev + spend);
    setEnergy((prev) => Math.max(0, prev - spend));

    const id = Date.now() + Math.random();
    setFloatingTexts((prev) => [...prev, { id, value: spend, x, y }]);
    setTimeout(() => {
      setFloatingTexts((prev) => prev.filter((t) => t.id !== id));
    }, 1000);

    // отправляем «сырые» клики (ровно сколько потратили энергии)
    addClicks(spend);
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
        {energy < maxEnergy && timeToFullEnergy && (
          <p className="text-xs mt-1 text-[#89dfff]">
            {t('full_in')} {timeToFullEnergy}
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

      {/* <button onClick={forceFlush} className="mt-4 px-3 py-2 rounded bg-[#0d273d] text-[#7ee9ff]">
        Sync now
      </button> */}
    </div>
  );
};

export default Clicker;
















































































