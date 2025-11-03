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

// 🔒 Kill switch: отключаем челлендж
const CHALLENGE_HARD_DISABLED = true;

// ---- boosters settings ----
const DAILY_CLAIM_LIMIT_PER_TYPE = 3;       // ← по 3 на каждый тип (🎁 и 🚀)
const SPAWN_SHOW_MS = 4500;                 // сколько висит бустер
// ↓ окна появления: ровно 1 час
const RESPAWN_MISSED_MIN_H = 1;             // если не пойман — через 1 час
const RESPAWN_MISSED_MAX_H = 1;
const RESPAWN_CLAIMED_MIN_H = 1;            // если пойман — следующая попытка через 1 час
const RESPAWN_CLAIMED_MAX_H = 1;

type SpawnedBooster =
  | { kind: 'coins'; id: number; x: number; y: number; expiresAt: number }
  | { kind: 'mult'; id: number; x: number; y: number; expiresAt: number };

// утилиты даты и стораджа (по локальным суткам устройства)
const todayKey = () => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${dd}`;
};
const lsKey = (base: string) => `gappick:${base}:${todayKey()}`;
const randHours = (minH: number, maxH: number) => {
  const ms = (minH * 3600 + Math.random() * (maxH - minH) * 3600) * 1000;
  return Math.round(ms);
};

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

  // челлендж (отключен kill switch'ом)
  const [challengeLoading] = useState(false);

  // ---- boosters UI/logic state ----
  const [spawned, setSpawned] = useState<SpawnedBooster | null>(null);
  const [tempMultUntil, setTempMultUntil] = useState<number | null>(null);
  const spawnTimer = useRef<number | null>(null);

  // раздельный учёт попыток по типам за сегодня + «когда можно снова показывать»
  const [coinsClaimsUsed, setCoinsClaimsUsed] = useState<number>(() => {
    const raw = localStorage.getItem(lsKey('boosters:coinsClaimsUsed'));
    return raw ? Number(raw) || 0 : 0;
  });
  const [multClaimsUsed, setMultClaimsUsed] = useState<number>(() => {
    const raw = localStorage.getItem(lsKey('boosters:multClaimsUsed'));
    return raw ? Number(raw) || 0 : 0;
  });
  const [nextSpawnAt, setNextSpawnAt] = useState<number>(() => {
    const raw = localStorage.getItem(lsKey('boosters:nextSpawnAt'));
    return raw ? Number(raw) || 0 : 0;
  });

  // сброс локальных ключей при смене суток
  useEffect(() => {
    const id = window.setInterval(() => {
      const k1 = lsKey('boosters:coinsClaimsUsed');
      const k2 = lsKey('boosters:multClaimsUsed');
      const k3 = lsKey('boosters:nextSpawnAt');
      if (!localStorage.getItem(k1)) setCoinsClaimsUsed(0);
      if (!localStorage.getItem(k2)) setMultClaimsUsed(0);
      if (!localStorage.getItem(k3)) setNextSpawnAt(0);
    }, 60_000);
    return () => window.clearInterval(id);
  }, []);

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

  // временный множитель x10, если активирован бустер
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

  // ---- boosters scheduling ----
  const allLimitsReached =
    coinsClaimsUsed >= DAILY_CLAIM_LIMIT_PER_TYPE &&
    multClaimsUsed >= DAILY_CLAIM_LIMIT_PER_TYPE;

  const canShowBoosterNow = () => {
    if (spawned) return false;
    if (allLimitsReached) return false;
    if (tempMultiplierActive > 1) return false; // не показываем второй, пока активен множитель
    const now = Date.now();
    return now >= nextSpawnAt;
  };

  const scheduleNextSpawn = (msFromNow: number) => {
    const at = Date.now() + msFromNow;
    setNextSpawnAt(at);
    localStorage.setItem(lsKey('boosters:nextSpawnAt'), String(at));
  };

  const spawnBooster = () => {
    // выбираем тип так, чтобы не предлагать исчерпанный
    const possible: Array<'coins' | 'mult'> = [];
    if (coinsClaimsUsed < DAILY_CLAIM_LIMIT_PER_TYPE) possible.push('coins');
    if (multClaimsUsed < DAILY_CLAIM_LIMIT_PER_TYPE) possible.push('mult');
    if (possible.length === 0) return;

    const kind = possible[Math.floor(Math.random() * possible.length)];
    const x = 10 + Math.random() * 80;
    const y = 10 + Math.random() * 80;
    const id = Date.now() + Math.random();
    const expiresAt = Date.now() + SPAWN_SHOW_MS;
    setSpawned({ kind, id, x, y, expiresAt });

    if (spawnTimer.current) window.clearTimeout(spawnTimer.current);
    spawnTimer.current = window.setTimeout(() => {
      // если не успели кликнуть — попытка НЕ сгорает
      setSpawned((cur) => (cur && cur.id === id ? null : cur));
      // повтор через 1 час
      scheduleNextSpawn(randHours(RESPAWN_MISSED_MIN_H, RESPAWN_MISSED_MAX_H));
    }, SPAWN_SHOW_MS) as unknown as number;
  };

  const maybeSpawnBooster = () => {
    if (!canShowBoosterNow()) return;
    // спавним только при кликах, когда «пришло время»
    spawnBooster();
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
        if (!res.ok) throw new Error('bad_response');
        const data = await res.json();
        if (data.status === 'ok') {
          const granted = Number(data.granted ?? 50000);
          setTotalXp((prev) => prev + granted);

          // +1 к использованным по типу 🎁
          const used = Math.min(DAILY_CLAIM_LIMIT_PER_TYPE, coinsClaimsUsed + 1);
          setCoinsClaimsUsed(used);
          localStorage.setItem(lsKey('boosters:coinsClaimsUsed'), String(used));

          // следующая попытка через 1 час
          scheduleNextSpawn(randHours(RESPAWN_CLAIMED_MIN_H, RESPAWN_CLAIMED_MAX_H));
        } else if (data.status === 'daily_limit_reached') {
          setCoinsClaimsUsed(DAILY_CLAIM_LIMIT_PER_TYPE);
          localStorage.setItem(lsKey('boosters:coinsClaimsUsed'), String(DAILY_CLAIM_LIMIT_PER_TYPE));
        }
      } else {
        const res = await fetch(`${API_BASE_URL}/api/boosters/claim/multiplier`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });
        if (!res.ok) throw new Error('bad_response');
        const data = await res.json();
        if (data.status === 'ok') {
          const expires = data.expires_at ? new Date(data.expires_at).getTime() : Date.now() + 15000;
          setTempMultUntil(expires);

          // +1 к использованным по типу 🚀
          const used = Math.min(DAILY_CLAIM_LIMIT_PER_TYPE, multClaimsUsed + 1);
          setMultClaimsUsed(used);
          localStorage.setItem(lsKey('boosters:multClaimsUsed'), String(used));

          // следующая попытка через 1 час
          scheduleNextSpawn(randHours(RESPAWN_CLAIMED_MIN_H, RESPAWN_CLAIMED_MAX_H));
        } else if (data.status === 'daily_limit_reached') {
          setMultClaimsUsed(DAILY_CLAIM_LIMIT_PER_TYPE);
          localStorage.setItem(lsKey('boosters:multClaimsUsed'), String(DAILY_CLAIM_LIMIT_PER_TYPE));
        }
      }
    } catch (e) {
      console.warn('Booster claim error', e);
      // при ошибке запроса не сжигаем попытку — дайте ещё шанс через 1 час
      scheduleNextSpawn(randHours(RESPAWN_MISSED_MIN_H, RESPAWN_MISSED_MAX_H));
    }
  };

  const handleMultiClick = (x: number, y: number) => {
    if (!telegramUser || loading || energy <= 0) return;

    // если пора — показываем бустер (строго по расписанию)
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

  // счётчик секунд для бейджа x10
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

  // если впервые за день зашли и nextSpawnAt не задан — поставим окно появления в ближайший час
  useEffect(() => {
    if (nextSpawnAt === 0) {
      scheduleNextSpawn(randHours(RESPAWN_MISSED_MIN_H, RESPAWN_MISSED_MAX_H));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const energyInt = Math.floor(smoothEnergy);

  return (
    <div className="w-full min-h-screen bg-[#131f2f] text-center flex flex-col items-center justify-start pt-8 px-4 text-[#00f0ff]">
      {/* Кнопка «Карта пользователя» в левом верхнем углу */}
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

        {/* всплывающие бустеры — чистые эмодзи 🎁/🚀 без фона, с мягкой пульсацией */}
        {spawned && (
          <div
            role="button"
            tabIndex={0}
            className="absolute z-50 text-4xl select-none booster-pulse"
            style={{
              left: `${spawned.x}%`,
              top: `${spawned.y}%`,
              transform: 'translate(-50%, -50%)',
              pointerEvents: 'auto',
              userSelect: 'none',
              lineHeight: 1,
              filter: 'drop-shadow(0 0 10px rgba(0,240,255,0.6)) drop-shadow(0 0 18px rgba(0,240,255,0.35))',
            }}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => { e.stopPropagation(); handleBoosterClick(spawned); }}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); handleBoosterClick(spawned); } }}
            aria-label={spawned.kind === 'coins'
              ? t('boosters.coin_label', { defaultValue: 'Gift booster' })
              : t('boosters.mult_label', { defaultValue: 'Rocket booster' })}
            title={spawned.kind === 'coins'
              ? t('boosters.coin_label', { defaultValue: 'Gift booster' })
              : t('boosters.mult_label', { defaultValue: 'Rocket booster' })}
          >
            <span
              style={{
                textShadow:
                  '0 0 10px rgba(0,240,255,0.7), 0 0 18px rgba(0,240,255,0.45), 0 0 28px rgba(0,240,255,0.35)',
                display: 'inline-block',
              }}
            >
              {spawned.kind === 'coins' ? '🎁' : '🚀'}
            </span>
          </div>
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
            0%   { transform: translate(-50%, -50%) scale(1); }
            50%  { transform: translate(-50%, -50%) scale(1.12); }
            100% { transform: translate(-50%, -50%) scale(1); }
          }
          .booster-pulse {
            animation: pulsePop 0.9s ease-in-out infinite;
          }
        `}</style>
      </div>

      {/* Заглушка для кнопки задания */}
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





























































































