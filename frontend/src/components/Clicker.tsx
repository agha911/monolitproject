import React, { useState, useEffect, useMemo, useRef } from 'react';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';
import MainButton from './MainButton';
import API_BASE_URL from './config';
import { useClickBuffer, FlushResponse } from '../hooks/useClickBuffer';
import { useAnimatedInt } from '../hooks/useAnimatedInt';
import UserCard from './UserCard';

// ---- boosters settings ----
const DAILY_CLAIM_LIMIT_PER_TYPE = 3; // по 3 на каждый тип (🎁 и 🚀)
const SPAWN_SHOW_MS = 4500;           // сколько висит бустер после появления

type SpawnedBooster =
  | { kind: 'coins'; id: number; x: number; y: number; expiresAt: number }
  | { kind: 'mult'; id: number; x: number; y: number; expiresAt: number };

const Clicker: React.FC = () => {
  const { t } = useTranslation();

  const [telegramUser, setTelegramUser] = useState<any | null>(null);
  const [totalXp, setTotalXp] = useState(0);
  const [energy, setEnergy] = useState(1000);
  const smoothEnergy = useAnimatedInt(energy, { speedPerUnit: 8, minDuration: 120, maxDuration: 600 });
  const [maxEnergy, setMaxEnergy] = useState(1000);

  const [clickBoost, setClickBoost] = useState(1);
  const [nickname, setNickname] = useState<string | null>(null);
  const [invitedFriends, setInvitedFriends] = useState<number>(0);
  const [ratingPosition, setRatingPosition] = useState<number | null>(null);
  const [ratingTotalPlayers, setRatingTotalPlayers] = useState<number | null>(null);

  const [lastEnergyUpdate, setLastEnergyUpdate] = useState<Date | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [clicks, setClicks] = useState(0);
  const [deltaXp, setDeltaXp] = useState(0);

  const [tempMultUntil, setTempMultUntil] = useState<number | null>(null);

  const [spawned, setSpawned] = useState<SpawnedBooster | null>(null);

  const [serverSeq, setServerSeq] = useState<number | null>(null);
  const [seqReady, setSeqReady] = useState(false);
  const lastFlushTimeRef = useRef<number>(0);

  const [flushError, setFlushError] = useState<string | null>(null);

  const [wasOffline, setWasOffline] = useState(false);

  const [energyDepletedShown, setEnergyDepletedShown] = useState(false);

  const { buffer, addClick, flushBuffer, clearBuffer } = useClickBuffer({
    onFlushed: (resp: FlushResponse) => {
      if (typeof resp.total_xp === 'number') {
        setTotalXp(resp.total_xp);
      }
      if (typeof resp.energy === 'number') {
        setEnergy(resp.energy);
      }
      setFlushError(null);
      setWasOffline(false);
    },
    onError: (err) => {
      console.error('Flush error', err);
      setFlushError('Синхронизация с сервером временно недоступна');
      setWasOffline(true);
    },
  });

  // ---- boosters daily tracking (локально, но день = UTC, как на бэке)
  // Используем UTC-день, чтобы совпадать с логикой бэкенда
  const todayStr = new Date().toISOString().slice(0, 10); // YYYY-MM-DD в UTC
  const coinsKey = `gappick:boosters:coinsClaimsUsed:${todayStr}`;
  const multKey  = `gappick:boosters:multClaimsUsed:${todayStr}`;

  const [coinsClaimsUsed, setCoinsClaimsUsed] = useState<number>(() => {
    const raw = localStorage.getItem(coinsKey);
    return raw ? Number(raw) || 0 : 0;
  });
  const [multClaimsUsed, setMultClaimsUsed] = useState<number>(() => {
    const raw = localStorage.getItem(multKey);
    return raw ? Number(raw) || 0 : 0;
  });

  // флаги «в этом сеансе уже показывали»
  const [sessionCoinsSpawned, setSessionCoinsSpawned] = useState(false);
  const [sessionMultSpawned, setSessionMultSpawned] = useState(false);

  // авто-обновление суточных счётчиков при смене даты (раз в минуту, по UTC)
  useEffect(() => {
    const id = window.setInterval(() => {
      const nowStr = new Date().toISOString().slice(0, 10);
      const cKey = `gappick:boosters:coinsClaimsUsed:${nowStr}`;
      const mKey = `gappick:boosters:multClaimsUsed:${nowStr}`;
      const cRaw = localStorage.getItem(cKey);
      const mRaw = localStorage.getItem(mKey);
      setCoinsClaimsUsed(cRaw ? Number(cRaw) || 0 : 0);
      setMultClaimsUsed(mRaw ? Number(mRaw) || 0 : 0);
    }, 60_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    WebApp.ready();
    const user = WebApp.initDataUnsafe?.user;
    if (user) setTelegramUser(user);
    else alert('Xəta: Telegram istifadəçi məlumatlarını almaq mümkün olmadı.');
  }, []);

  const seqStorageKey = useMemo(() => {
    const telegramId = WebApp.initDataUnsafe?.user?.id;
    return telegramId ? `gappick:lastServerSeq:${telegramId}` : 'gappick:lastServerSeq:anon';
  }, []);

  // исправлено: useState без deps + отдельный useEffect, который читает localStorage
  const [lastClientSeq, setLastClientSeq] = useState<number>(0);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(seqStorageKey);
      setLastClientSeq(saved ? Number(saved) : 0);
    } catch {
      setLastClientSeq(0);
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

        setNickname(data.nickname ?? null);
        setInvitedFriends(data.invited_friends_count ?? 0);
        setRatingPosition(data.rating_position ?? null);
        setRatingTotalPlayers(data.rating_total_players ?? null);

        const s = Number(data.last_client_seq ?? 0);
        setServerSeq(s);
        try {
          localStorage.setItem(seqStorageKey, String(s));
        } catch {}

        setSeqReady(true);
        setLoading(false);
      } catch (e) {
        console.error(e);
        setError('Xəta baş verdi. Лütfən, daha sonra yenidən cəhd edin.');
        setLoading(false);
      }
    })();
  }, [telegramUser, seqStorageKey]);

  useEffect(() => {
    if (!lastEnergyUpdate) return;

    const updateEnergyFromServerTime = () => {
      if (!lastEnergyUpdate) return;
      const now = new Date();
      const diffMs = now.getTime() - lastEnergyUpdate.getTime();
      const diffMinutes = Math.floor(diffMs / 60000);

      if (diffMinutes <= 0) return;

      const ENERGY_RECOVERY_INTERVAL_MINUTES = 1;
      const ENERGY_PER_INTERVAL = 1;
      const intervals = Math.floor(diffMinutes / ENERGY_RECOVERY_INTERVAL_MINUTES);

      if (intervals <= 0) return;

      setEnergy((prev) => {
        const recovered = prev + intervals * ENERGY_PER_INTERVAL;
        const capped = Math.min(recovered, maxEnergy);
        return capped;
      });

      setLastEnergyUpdate((prev) => {
        if (!prev) return prev;
        const newDate = new Date(prev.getTime() + intervals * ENERGY_RECOVERY_INTERVAL_MINUTES * 60000);
        return newDate;
      });
    };

    updateEnergyFromServerTime();
    const id = window.setInterval(updateEnergyFromServerTime, 30_000);

    return () => clearInterval(id);
  }, [lastEnergyUpdate, maxEnergy]);

  const energyInt = smoothEnergy;

  const currentMultiplier = useMemo(() => {
    const now = Date.now();
    if (tempMultUntil && tempMultUntil > now) return 10;
    return 1;
  }, [tempMultUntil]);

  const canClick = energy > 0;

  const flushIfNeeded = async () => {
    if (!seqReady || buffer.length === 0) return;

    const now = Date.now();
    if (now - lastFlushTimeRef.current < 500) return;
    lastFlushTimeRef.current = now;

    const nextSeqStart = lastClientSeq + 1;
    const eventsWithSeq = buffer.map((ev, index) => ({
      ...ev,
      seq: nextSeqStart + index,
    }));

    setLastClientSeq(nextSeqStart + buffer.length - 1);
    try {
      localStorage.setItem(seqStorageKey, String(nextSeqStart + buffer.length - 1));
    } catch (e) {
      console.warn('Cannot persist seq', e);
    }

    await flushBuffer(eventsWithSeq, WebApp.initData);
  };

  useEffect(() => {
    if (!canClick || !seqReady || buffer.length === 0) return;
    flushIfNeeded();
  }, [buffer, canClick, seqReady]);

  const handleClick = () => {
    if (!canClick) {
      if (!energyDepletedShown) {
        WebApp.HapticFeedback.notificationOccurred('warning');
        setEnergyDepletedShown(true);
        setTimeout(() => setEnergyDepletedShown(false), 2000);
      }
      return;
    }

    const now = Date.now();
    const clickValue = clickBoost * currentMultiplier;

    addClick({
      value: clickValue,
      ts: now,
      tg_init_data: WebApp.initData,
    });

    setClicks((prev) => prev + 1);
    setDeltaXp((prev) => prev + clickValue);
    setEnergy((prev) => Math.max(prev - 1, 0));

    flushIfNeeded();
  };

  const spawnRandomBooster = () => {
    if (!canClick) return;
    if (!seqReady) return;

    const shouldSpawnCoin =
      !sessionCoinsSpawned &&
      coinsClaimsUsed < DAILY_CLAIM_LIMIT_PER_TYPE &&
      Math.random() < 0.02;

    const shouldSpawnMult =
      !sessionMultSpawned &&
      multClaimsUsed < DAILY_CLAIM_LIMIT_PER_TYPE &&
      Math.random() < 0.02;

    if (!shouldSpawnCoin && !shouldSpawnMult) return;

    const kind: SpawnedBooster =
      shouldSpawnCoin && shouldSpawnMult
        ? Math.random() < 0.5
          ? { kind: 'coins', id: Date.now(), x: Math.random() * 80 + 10, y: Math.random() * 60 + 20, expiresAt: Date.now() + SPAWN_SHOW_MS }
          : { kind: 'mult', id: Date.now(), x: Math.random() * 80 + 10, y: Math.random() * 60 + 20, expiresAt: Date.now() + SPAWN_SHOW_MS }
        : shouldSpawnCoin
        ? { kind: 'coins', id: Date.now(), x: Math.random() * 80 + 10, y: Math.random() * 60 + 20, expiresAt: Date.now() + SPAWN_SHOW_MS }
        : { kind: 'mult', id: Date.now(), x: Math.random() * 80 + 10, y: Math.random() * 60 + 20, expiresAt: Date.now() + SPAWN_SHOW_MS };

    if (kind.kind === 'coins') setSessionCoinsSpawned(true);
    if (kind.kind === 'mult') setSessionMultSpawned(true);

    setSpawned(kind);

    window.setTimeout(() => {
      setSpawned((cur) => (cur && cur.id === kind.id ? null : cur));
    }, SPAWN_SHOW_MS) as unknown as number;
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

          // предпочитаем реальное значение с бэкенда
          const usedFromServer = typeof data.used_today === 'number' ? data.used_today : null;
          const used = usedFromServer !== null
            ? Math.min(DAILY_CLAIM_LIMIT_PER_TYPE, usedFromServer)
            : Math.min(DAILY_CLAIM_LIMIT_PER_TYPE, coinsClaimsUsed + 1);
          setCoinsClaimsUsed(used);
          localStorage.setItem(coinsKey, String(used));
        } else if (data.status === 'daily_limit_reached') {
          const usedFromServer = typeof data.used_today === 'number' ? data.used_today : DAILY_CLAIM_LIMIT_PER_TYPE;
          const used = Math.min(DAILY_CLAIM_LIMIT_PER_TYPE, usedFromServer);
          setCoinsClaimsUsed(used);
          localStorage.setItem(coinsKey, String(used));
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

          const usedFromServer = typeof data.used_today === 'number' ? data.used_today : null;
          const used = usedFromServer !== null
            ? Math.min(DAILY_CLAIM_LIMIT_PER_TYPE, usedFromServer)
            : Math.min(DAILY_CLAIM_LIMIT_PER_TYPE, multClaimsUsed + 1);
          setMultClaimsUsed(used);
          localStorage.setItem(multKey, String(used));
        } else if (data.status === 'daily_limit_reached') {
          const usedFromServer = typeof data.used_today === 'number' ? data.used_today : DAILY_CLAIM_LIMIT_PER_TYPE;
          const used = Math.min(DAILY_CLAIM_LIMIT_PER_TYPE, usedFromServer);
          setMultClaimsUsed(used);
          localStorage.setItem(multKey, String(used));
        }
      }
    } catch (e) {
      console.warn('Booster claim error', e);
    }
  };

  useEffect(() => {
    if (!canClick || !seqReady) return;
    if (spawned) return;

    const id = window.setInterval(() => {
      if (Math.random() < 0.05) {
        spawnRandomBooster();
      }
    }, 6000);

    return () => clearInterval(id);
  }, [canClick, seqReady, spawned, coinsClaimsUsed, multClaimsUsed, sessionCoinsSpawned, sessionMultSpawned]);

  const resetBoostersSession = () => {
    setSessionCoinsSpawned(false);
    setSessionMultSpawned(false);
  };

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (!document.hidden) {
        resetBoostersSession();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

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
    const id = window.setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [tempMultUntil]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-[#050816] to-[#021019] flex items-center justify-center text-white">
        <div className="text-center space-y-2">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#00f2ff] mx-auto" />
          <div className="text-sm text-[#9be1ff]">
            {t('loading', { defaultValue: 'Yüklənir...' })}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-[#050816] to-[#021019] flex items-center justify-center text-white px-4">
        <div className="max-w-xs text-center space-y-3">
          <div className="text-red-400 font-semibold text-sm">Xəta</div>
          <div className="text-sm text-[#fca5a5]">{error}</div>
          <button
            className="mt-2 px-4 py-2 rounded-lg bg-[#0ea5e9] text-xs font-semibold text-black hover:bg-[#38bdf8] transition"
            onClick={() => window.location.reload()}
          >
            Yenidən cəhd et
          </button>
        </div>
      </div>
    );
  }

  const totalXpFormatted = useMemo(() => {
    return totalXp.toLocaleString('en-US').replace(/,/g, ' ');
  }, [totalXp]);

  const deltaXpFormatted = useMemo(() => {
    if (!deltaXp) return '';
    const sign = deltaXp > 0 ? '+' : '';
    return `${sign}${deltaXp}`;
  }, [deltaXp]);

  useEffect(() => {
    if (deltaXp === 0) return;
    const id = window.setTimeout(() => setDeltaXp(0), 1000);
    return () => clearTimeout(id);
  }, [deltaXp]);

  return (
    <div
      className="min-h-screen bg-gradient-to-b from-[#050816] via-[#030712] to-[#020617] text-white flex flex-col items-center"
      onClick={handleClick}
    >
      <div className="w-full max-w-md px-4 pt-4 flex flex-col gap-3">
        <UserCard
          username={nickname ?? telegramUser?.username}
          totalXp={totalXp}
          invitedFriends={invitedFriends}
          ratingPosition={ratingPosition}
          ratingTotalPlayers={ratingTotalPlayers}
        />

        <div className="flex items-center justify-between text-xs text-[#9be1ff] mt-1">
          <span>
            {t('click_boost', { defaultValue: 'Klik gücü' })}: x{clickBoost}
          </span>
          <span>
            {t('multiplier', { defaultValue: 'Müvəqqəti x10' })}:{' '}
            {currentMultiplier > 1 ? (
              <span className="text-[#f97316] font-semibold">
                x10 · {multCountdown}s
              </span>
            ) : (
              <span className="opacity-60">x1</span>
            )}
          </span>
        </div>

        <div className="mb-3 flex items-center gap-2 text-xs">
          <span
            className={`px-2 py-1 rounded-full border ${
              coinsClaimsUsed >= DAILY_CLAIM_LIMIT_PER_TYPE
                ? 'opacity-60 border-[#2b526e] text-[#6ea6c7]'
                : 'border-[#1f3b57] text-[#a0f6ff]'
            }`}
            title="Gift boosters today"
          >
            🎁 {coinsClaimsUsed}/{DAILY_CLAIM_LIMIT_PER_TYPE}
          </span>
          <span
            className={`px-2 py-1 rounded-full border ${
              multClaimsUsed >= DAILY_CLAIM_LIMIT_PER_TYPE
                ? 'opacity-60 border-[#2b526e] text-[#6ea6c7]'
                : 'border-[#1f3b57] text-[#a0f6ff]'
            }`}
            title="Rocket boosters today"
          >
            🚀 {multClaimsUsed}/{DAILY_CLAIM_LIMIT_PER_TYPE}
          </span>
        </div>

        <div className="my-4 w-full max-w-md">
          <label className="block mb-1 text-sm text-[#7ee9ff]">
            {t('energy')}: {energyInt} / {maxEnergy}
          </label>
          <div className="w-full h-4 bg-[#0d273d] rounded overflow-hidden shadow-inner">
            <div
              className="h-full bg-gradient-to-r from-[#7af9ff] to-[#0ea5e9] transition-all duration-300"
              style={{ width: `${(energyInt / maxEnergy) * 100}%` }}
            />
          </div>
        </div>

        <div className="mt-2 flex flex-col items-center">
          <div className="relative inline-flex items-center justify-center">
            <MainButton onClick={handleClick} disabled={!canClick} />
            {spawned && (
              <button
                type="button"
                className="absolute z-20 w-14 h-14 rounded-full border-2 border-[#22d3ee] bg-[#020617]/90 flex items-center justify-center text-2xl select-none"
                style={{
                  left: `${spawned.x}%`,
                  top: `${spawned.y}%`,
                  transform: 'translate(-50%, -50%)',
                  pointerEvents: 'auto',
                  userSelect: 'none',
                  lineHeight: 1,
                  filter:
                    'drop-shadow(0 0 10px rgba(0,240,255,0.6)) drop-shadow(0 0 18px rgba(0,240,255,0.35))',
                }}
                onMouseDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  handleBoosterClick(spawned);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    e.stopPropagation();
                    handleBoosterClick(spawned);
                  }
                }}
                aria-label={
                  spawned.kind === 'coins'
                    ? t('boosters.coin_label', { defaultValue: 'Gift booster' })
                    : t('boosters.mult_label', { defaultValue: 'Rocket booster' })
                }
              >
                {spawned.kind === 'coins' ? '🎁' : '🚀'}
              </button>
            )}
          </div>

          <div className="mt-3 text-center">
            <div className="text-2xl font-bold text-[#e5f9ff] tracking-wide">
              {totalXpFormatted}
            </div>
            {deltaXp !== 0 && (
              <div className="text-sm text-[#4ade80] mt-1">
                {t('earned', { defaultValue: 'Qazanıldı' })}: {deltaXpFormatted}
              </div>
            )}
          </div>
        </div>

        {flushError && (
          <div className="mt-3 text-xs text-[#facc15] bg-[#451a03]/60 border border-[#78350f] rounded-lg px-3 py-2">
            {flushError}
          </div>
        )}

        {wasOffline && !flushError && (
          <div className="mt-2 text-xs text-[#e5e7eb] opacity-80">
            İnternet bağlantısında qısa fasilə oldu. Məlumatlar bərpa olunur...
          </div>
        )}

        {energyDepletedShown && (
          <div className="mt-2 text-xs text-[#fecaca]">
            Enerji bitib. Bir azdan bərpa olacaq.
          </div>
        )}
      </div>
    </div>
  );
};

export default Clicker;


































































































