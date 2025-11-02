import React, { useState, useEffect, useMemo, useRef } from 'react';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';
import MainButton from './MainButton';
import API_BASE_URL from './config';
import { useClickBuffer, FlushResponse } from '../hooks/useClickBuffer';
import { useAnimatedInt } from '../hooks/useAnimatedInt';
import UserCard from './UserCard';

type ChallengeDay = {
  day_index: number;
  tiktok_url: string;
  question: string;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  reward_watch: number;
  reward_answer: number;
  is_active: boolean;
};

const CHALLENGE_HARD_DISABLED = true;

type SpawnedBooster =
  | { kind: 'coins'; id: number; x: number; y: number; expiresAt: number }
  | { kind: 'mult'; id: number; x: number; y: number; expiresAt: number };

const Clicker: React.FC = () => {
  const { t } = useTranslation();

  const [telegramUser, setTelegramUser] = useState<any | null>(null);
  const [totalXp, setTotalXp] = useState(0);
  const [energy, setEnergy] = useState(1000);
  const smoothEnergy = useAnimatedInt(energy, {
    speedPerUnit: 8,
    minDuration: 120,
    maxDuration: 600,
  });
  const [maxEnergy, setMaxEnergy] = useState(1000);
  const [lastEnergyUpdate, setLastEnergyUpdate] = useState<Date | null>(null);
  const [timeToFullEnergy, setTimeToFullEnergy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [clickBoost, setClickBoost] = useState(1);
  const [floatingTexts, setFloatingTexts] = useState<any[]>([]);
  const [serverSeq, setServerSeq] = useState<number | null>(null);
  const [seqReady, setSeqReady] = useState(false);
  const [showUserCard, setShowUserCard] = useState(false);

  // boosters UI state
  const [spawned, setSpawned] = useState<SpawnedBooster | null>(null);
  const [tempMultUntil, setTempMultUntil] = useState<number | null>(null);
  const spawnTimer = useRef<number | null>(null);

  // челлендж (отключен)
  const [challengeLoading] = useState(false);

  useEffect(() => {
    WebApp.ready();
    const user = WebApp.initDataUnsafe?.user;
    if (user) setTelegramUser(user);
    else alert('Xəta: Telegram istifadəçi məlumatlarını almaq mümkün olmadı.');
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

    (async () => {
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
        console.error('İstifadəçinin ilkinləşdirilməsində xəta:', error);
        setSeqReady(false);
      }
    })();
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
        console.error('Auto yeniləmədə xəta:', err);
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [telegramUser, energy, maxEnergy, serverSeq, seqStorageKey]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (!lastEnergyUpdate || energy >= maxEnergy) {
        setTimeToFullEnergy(null);
        return;
      }
      const now = new Date();
      const msPassed = now.getTime() - (lastEnergyUpdate?.getTime?.() ?? 0);
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
    if (data.status === "ok") {
      setEnergy(data.energy);
      setTotalXp(data.total_xp);
      setServerSeq(Number(data.server_seq ?? 0));
    } else if (data.status === "noop") {
      return;
    } else {
      try {
        const res = await fetch(`${API_BASE_URL}/api/game/progress`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });
        const p = await res.json();
        setEnergy(p.energy);
        setTotalXp(p.total_xp ?? 0);
        setLastEnergyUpdate(p.lastEnergyUpdate ? new Date(p.lastEnergyUpdate) : null);
        setMaxEnergy(p.max_energy ?? 1000);
        setClickBoost((p.click_boost_level ?? 0) + 1);
        setServerSeq(Number(p.last_client_seq ?? 0));
      } catch (e) {
        console.warn("Xəta sonrası yeniləmə alınmadı", e);
      }
    }
  };

  const tempMultiplierActive = tempMultUntil !== null && Date.now() < tempMultUntil ? 10 : 1;
  const effectiveBoost = clickBoost * tempMultiplierActive;

  const { addClicks } = useClickBuffer({
    initData: WebApp.initData,
    sessionId,
    onReconcile,
    enabled: seqReady && !!telegramUser,
    flushEveryMs: 200,
    threshold: 50,
    initialSeq: Math.max(serverSeq ?? 0, initialLocalSeq),
    maxBatch: 50,
    lockKey: userId,
    seqStorageKey: seqStorageKey as any,
    canSend: energy > 0
  });

  // ——— booster spawn helper ———
  const maybeSpawnBooster = () => {
    if (spawned) return; // один за раз
    if (Math.random() < 0.04) {
      const kind: 'coins' | 'mult' = Math.random() < 0.5 ? 'coins' : 'mult';
      const x = 10 + Math.random() * 80;
      const y = 10 + Math.random() * 80;
      const id = Date.now() + Math.random();
      const expiresAt = Date.now() + 4000; // 4s
      setSpawned({ kind, id, x, y, expiresAt } as SpawnedBooster);

      if (spawnTimer.current) window.clearTimeout(spawnTimer.current);
      spawnTimer.current = window.setTimeout(() => {
        setSpawned((cur) => (cur && cur.id === id ? null : cur));
      }, 4000) as unknown as number;
    }
  };

  const handleBoosterClick = async (b: SpawnedBooster) => {
    setSpawned(null);
    if (!telegramUser) return;

    try {
      if (b.kind === 'coins') {
        const res = await fetch(`${API_BASE_URL}/api/boosters/claim/coins`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
          const granted = Number(data.granted ?? 50000);
          setTotalXp((prev) => prev + granted);
          alert(t('boosters.coin_granted', { defaultValue: 'Bonus +50K added!' }));
        } else if (data.status === 'daily_limit_reached') {
          console.info('Daily limit reached');
        } else {
          alert(t('error', { defaultValue: 'Error' }));
        }
      } else {
        const res = await fetch(`${API_BASE_URL}/api/boosters/claim/multiplier`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
          const expires = data.expires_at ? new Date(data.expires_at).getTime() : Date.now() + 15000;
          setTempMultUntil(expires);
        } else if (data.status === 'daily_limit_reached') {
          console.info('Daily limit reached');
        } else {
          alert(t('error', { defaultValue: 'Error' }));
        }
      }
    } catch (e) {
      console.warn('Booster claim error', e);
    }
  };

  // ——— main click ———
  const handleMultiClick = (x: number, y: number) => {
    if (!telegramUser || loading || energy <= 0) return;

    // шанс появления бустера при клике
    maybeSpawnBooster();

    const spend = Math.min(effectiveBoost, energy);
    if (spend <= 0) return;

    setTotalXp((prev) => prev + spend);
    setEnergy((prev) => Math.max(0, prev - spend));

    const id = Date.now() + Math.random();
    setFloatingTexts((prev) => [...prev, { id, value: spend, x, y }]);
    setTimeout(() => {
      setFloatingTexts((prev) => prev.filter((t) => t.id !== id));
    }, 1000);

    addClicks(spend);
  };

  // ——— x10 countdown ———
  const [multCountdown, setMultCountdown] = useState<number>(0);
  useEffect(() => {
    if (!tempMultUntil) {
      setMultCountdown(0);
      return;
    }
    const tick = () => {
      const left = Math.max(0, Math.ceil((tempMultUntil - Date.now()) / 1000));
      setMultCountdown(left);
      if (left <= 0) setTempMultUntil(null);
    };
    tick();
    const id = window.setInterval(tick, 250);
    return () => window.clearInterval(id);
  }, [tempMultUntil]);

  const energyInt = Math.floor(smoothEnergy);

  return (
    <div className="w-full min-h-screen bg-[#131f2f] text-center flex flex-col items-center justify-start pt-8 px-4 text-[#00f0ff]">
      {/* кнопка «Карта» */}
      <button
        className="fixed top-3 left-3 z-50 w-9 h-9 rounded-full bg-black/80 text-white shadow flex items-center justify-center active:scale-95"
        onClick={() => setShowUserCard(true)}
        aria-label={t('userCard.open', { defaultValue: 'User card' })}
        title={t('userCard.open', { defaultValue: 'User card' })}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M12 12c2.761 0 5-2.686 5-6s-2.239-6-5-6-5 2.686-5 6 2.239 6 5 6Zm0 2c-4.418 0-8 2.91-8 6.5V22h16v-1.5C20 16.91 16.418 14 12 14Z" fill="currentColor"/>
        </svg>
      </button>

      <h2 className="text-2xl font-bold mb-2 drop-shadow-md">$GAP: {totalXp}</h2>

      <div className="text-sm text-[#7ee9ff] mb-2 flex items-center gap-2">
        <span>x{clickBoost} {t('boost', { defaultValue: 'boost' })}</span>
        {tempMultiplierActive > 1 && (
          <span className="px-2 py-0.5 rounded-full bg-[#00f0ff] text-[#0e1a2b] text-xs font-bold">
            x10 · {multCountdown}s
          </span>
        )}
      </div>

      <div className="my-4 w-full max-w-md">
        <label className="block mb-1 text-sm text-[#7ee9ff]">
          {t('energy')}: {energyInt} / {maxEnergy}
        </label>
        <div className="w-full h-4 bg-[#0d273d] rounded overflow-hidden shadow-inner">
          <div
            className="h-full bg-gradient-to-r from-[#7af9ff] to-[#00f0ff]"
            style={{ width: `${Math.min((smoothEnergy / maxEnergy) * 100, 100)}%`, transition: "none" }}
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
          <MainButton energy={energyInt} onMultiClick={handleMultiClick} />
        </div>

        {/* всплывающие бустеры — пульсирующие 🎁/🚀 */}
        {spawned && (
          <button
            className="absolute w-12 h-12 rounded-full text-xl grid place-items-center active:scale-95 booster-pulse"
            style={{
              left: `${spawned.x}%`,
              top: `${spawned.y}%`,
              transform: 'translate(-50%, -50%)',
              background: spawned.kind === 'coins' ? '#1EE38F' : '#FFC800',
              color: '#0e1a2b'
            }}
            onClick={() => handleBoosterClick(spawned)}
            aria-label={spawned.kind === 'coins'
              ? t('boosters.coin_label', { defaultValue: 'Gift booster' })
              : t('boosters.mult_label', { defaultValue: 'Rocket booster' })}
            title={spawned.kind === 'coins'
              ? t('boosters.coin_label', { defaultValue: 'Gift booster' })
              : t('boosters.mult_label', { defaultValue: 'Rocket booster' })}
          >
            {spawned.kind === 'coins' ? '🎁' : '🚀'}
          </button>
        )}

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

        {/* Локальные анимации */}
        <style>{`
          @keyframes floatUpFade {
            0% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
            100% { opacity: 0; transform: translate(-50%, -100%) scale(1.2); }
          }
          @keyframes pulsePop {
            0%   { transform: translate(-50%, -50%) scale(1); box-shadow: 0 0 0 0 rgba(0,240,255,0.0); }
            50%  { transform: translate(-50%, -50%) scale(1.1); box-shadow: 0 0 18px 6px rgba(0,240,255,0.35); }
            100% { transform: translate(-50%, -50%) scale(1); box-shadow: 0 0 0 0 rgba(0,240,255,0.0); }
          }
          .booster-pulse {
            animation: pulsePop 0.9s ease-in-out infinite;
          }
        `}</style>
      </div>

      {!challengeLoading && (
        <div className="mt-4 w-full max-w-md">
          <button
            className="w-full px-4 py-2 rounded-xl bg-[#0d273d] text-[#7aa1b7] border border-[#1f3b57] opacity-60 cursor-not-allowed"
            disabled
          >
            🎥 Günün tapşırığı (deaktivdir)
          </button>
          <div className="mt-2 text-[11px] text-[#7aa1b7]">
            Turnir başa çatıb. Yeni tapşırıqlar tezliklə əlavə olunacaq.
          </div>
        </div>
      )}

      {showUserCard && <UserCard onClose={() => setShowUserCard(false)} />}
    </div>
  );
};

export default Clicker;


























































































