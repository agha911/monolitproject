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
      setLastClient

































































































