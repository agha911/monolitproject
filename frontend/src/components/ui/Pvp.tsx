import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import WebApp from '@twa-dev/sdk';
import API_BASE_URL from '../config';

function getTelegramId(): number | null {
  const id = WebApp.initDataUnsafe?.user?.id;
  return typeof id === 'number' ? id : null;
}

async function apiRequest<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(opts?.headers || {}),
    },
    ...opts,
  });

  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    const msg = (data && (data.message || data.detail)) || `HTTP ${res.status}`;
    const err: any = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.payload = data;
    throw err;
  }
  return data as T;
}

type Screen = 'lobby' | 'duel' | 'result';
type DuelMode = 'live' | 'challenge';
type DuelPhase = 'prep' | 'active';
type Outcome = 'win' | 'lose' | 'draw' | 'unknown';

type TelemetryPayload = {
  client_started_at_ms?: number | null;
  client_finished_at_ms?: number | null;
  tap_count?: number;
  max_concurrent_touches?: number;
  avg_taps_per_sec?: number;
  peak_taps_per_sec?: number;
  send_batches_count?: number;
  had_pauses?: boolean;
  pause_count?: number;
  longest_pause_ms?: number;
};

type AntiCheatVerdict = {
  reported_clicks?: number | null;
  validated_clicks?: number | null;
  is_suspicious?: boolean | null;
  confidence?: number | null;
  score?: number | null;
  reason?: string | null;
  flags?: string[];
};

type PublicUser = {
  user_id?: number;
  id?: number;
  telegram_id?: number;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
};

const BOT_USERNAME = 'monolit_42_bot';
const PREP_SECONDS = 5;

// glow tuning
const GLOW_WINDOW_MS = 700;
const GLOW_MAX_CPS = 12;
const GLOW_DECAY_PER_TICK = 0.05;
const GLOW_TICK_MS = 45;
const GLOW_RISE_LERP = 0.12;

// telemetry tuning
const PAUSE_THRESHOLD_MS = 250;
const PEAK_WINDOW_MS = 1000;

function buildInviteLink(code: string) {
  return `https://t.me/${BOT_USERNAME}?startapp=pvp_${code}`;
}

function buildShareLink(url: string, text: string) {
  return `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;
}

function intOrZero(v: any): number {
  const n = Number(v);
  return Number.isFinite(n) ? Math.floor(n) : 0;
}

function numOrNull(v: any): number | null {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function pickVictories(me: any): number {
  const v = me?.pvp_victories ?? me?.victories ?? me?.pvp_weekly_victories ?? me?.weekly_victories ?? 0;
  return Number.isFinite(Number(v)) ? Number(v) : 0;
}

function pickBest(me: any): number {
  const b = me?.pvp_best_result ?? me?.best_result ?? me?.best ?? me?.pvp_best ?? 0;
  return Number.isFinite(Number(b)) ? Number(b) : 0;
}

function pickChallengeAttemptsLeft(obj: any): number | null {
  const keys = [
    'challenge_attempts_left',
    'challenge_attempts_remaining',
    'challenge_left',
    'pvp_challenge_attempts_left',
    'pvp_challenge_left',
    'attempts_left',
    'attempts_remaining',
    'remaining_attempts',
    'remaining_today',
  ];

  for (const k of keys) {
    if (obj && obj[k] != null) {
      const n = Number(obj[k]);
      if (Number.isFinite(n)) return Math.max(0, Math.floor(n));
    }
  }

  const nested = obj?.limits ?? obj?.challenge ?? obj?.pvp ?? null;
  if (nested && nested !== obj) return pickChallengeAttemptsLeft(nested);

  return null;
}

function formatUserLabel(u: any, fallbackId?: number | null) {
  if (!u && fallbackId != null) return `#${fallbackId}`;
  if (!u) return '—';

  const username = u?.username ? String(u.username).trim() : '';
  if (username) return `@${username}`;

  const fn = u?.first_name ? String(u.first_name).trim() : '';
  const ln = u?.last_name ? String(u.last_name).trim() : '';
  const full = `${fn} ${ln}`.trim();
  if (full) return full;

  const id = u?.user_id ?? u?.id ?? fallbackId;
  if (typeof id === 'number') return `#${id}`;

  return '—';
}

function normalizeOutcome(raw: any, meUserId?: number | null): Outcome {
  const s = String(raw?.status ?? raw?.outcome ?? raw?.result ?? raw?.state ?? '').toLowerCase();

  if (s.includes('win')) return 'win';
  if (s.includes('lose')) return 'lose';
  if (s.includes('draw') || s.includes('tie')) return 'draw';

  const winnerId =
    raw?.winner_user_id ?? raw?.winner_id ?? raw?.winner?.user_id ?? raw?.winner?.id ?? raw?.winnerUserId;
  const loserId =
    raw?.loser_user_id ?? raw?.loser_id ?? raw?.loser?.user_id ?? raw?.loser?.id ?? raw?.loserUserId;

  if (meUserId && typeof winnerId === 'number') return winnerId === meUserId ? 'win' : 'lose';
  if (meUserId && typeof loserId === 'number') return loserId === meUserId ? 'lose' : 'win';

  const won = raw?.won ?? raw?.is_winner ?? raw?.isWinner ?? raw?.is_win;
  if (typeof won === 'boolean') return won ? 'win' : 'lose';

  return 'unknown';
}

function extractNumber(raw: any, keys: string[]): number | null {
  for (const k of keys) {
    if (raw && raw[k] != null) {
      const n = Number(raw[k]);
      if (Number.isFinite(n)) return n;
    }
  }
  return null;
}

function parseServerError(e: any): { code?: string; message?: string } {
  const payload = e?.payload;
  if (payload && typeof payload === 'object') {
    const detail = payload.detail;
    if (detail && typeof detail === 'object') {
      return {
        code: detail.code || payload.code,
        message: detail.message || detail.detail || payload.message || payload.detail || payload.error,
      };
    }
    return { code: payload.code, message: payload.message || payload.detail || payload.error };
  }
  const msg = e?.message;
  if (typeof msg === 'string') {
    try {
      const j = JSON.parse(msg);
      if (j && typeof j === 'object') return { code: j.code, message: j.message || j.detail };
    } catch {}
  }
  return { message: typeof msg === 'string' ? msg : undefined };
}

function getUserId(u: any): number | null {
  const v = u?.user_id ?? u?.id;
  return typeof v === 'number' ? v : null;
}

function getEmbeddedLiveOpponent(matchInfo: any, meUserId: number | null): PublicUser | null {
  if (!matchInfo) return null;
  if (matchInfo?.opponent) return matchInfo.opponent;
  if (matchInfo?.opponent_user) return matchInfo.opponent_user;

  const p1 = matchInfo?.player1;
  const p2 = matchInfo?.player2;
  const p1Id = getUserId(p1) ?? matchInfo?.player1_id ?? null;
  const p2Id = getUserId(p2) ?? matchInfo?.player2_id ?? null;

  if (meUserId && p1Id === meUserId) return p2 ?? null;
  if (meUserId && p2Id === meUserId) return p1 ?? null;

  return null;
}

function getLiveVerdicts(raw: any, meUserId?: number | null) {
  const anti = raw?.anti_cheat ?? raw?.result?.anti_cheat ?? null;
  if (!anti) return { me: null as AntiCheatVerdict | null, opponent: null as AntiCheatVerdict | null };

  const p1 = anti?.player1 ?? null;
  const p2 = anti?.player2 ?? null;

  const p1Id = raw?.player1_id ?? raw?.result?.player1_id ?? null;
  const p2Id = raw?.player2_id ?? raw?.result?.player2_id ?? null;

  if (meUserId && p1Id === meUserId) return { me: p1, opponent: p2 };
  if (meUserId && p2Id === meUserId) return { me: p2, opponent: p1 };

  return { me: p1, opponent: p2 };
}

function resolveLiveClicks(raw: any, meUserId?: number | null) {
  const src = raw?.result ?? raw;
  const p1Id = src?.player1_id;
  const p2Id = src?.player2_id;
  const p1Clicks = extractNumber(src, ['player1_clicks']);
  const p2Clicks = extractNumber(src, ['player2_clicks']);

  if (meUserId && p1Id === meUserId) {
    return { myClicks: p1Clicks, opponentClicks: p2Clicks };
  }
  if (meUserId && p2Id === meUserId) {
    return { myClicks: p2Clicks, opponentClicks: p1Clicks };
  }

  return { myClicks: p1Clicks, opponentClicks: p2Clicks };
}

function getChallengeVerdict(raw: any): AntiCheatVerdict | null {
  return raw?.anti_cheat ?? raw?.result?.anti_cheat ?? null;
}

function formatFlags(flags?: string[]) {
  if (!Array.isArray(flags) || flags.length === 0) return '—';
  return flags.join(', ');
}

const Pvp: React.FC = () => {
  const { t } = useTranslation();

  const telegramId = useMemo(() => getTelegramId(), []);
  const canUse = !!telegramId && !!WebApp.initData;

  const [loading, setLoading] = useState(false);

  const [error, setError] = useState<string>('');

  const [config, setConfig] = useState<any>(null);

  const [meUserId, setMeUserId] = useState<number | null>(null);
  const [meInfo, setMeInfo] = useState<any>(null);

  const [weeklySeason, setWeeklySeason] = useState<any>(null);
  const [weeklyItems, setWeeklyItems] = useState<any[]>([]);
  const [weeklyLoading, setWeeklyLoading] = useState<boolean>(false);

  const [createdInvite, setCreatedInvite] = useState<any>(null);
  const invitePollRef = useRef<number | null>(null);

  const [matchInfo, setMatchInfo] = useState<any>(null);

  const [screen, setScreen] = useState<Screen>('lobby');
  const [duelMode, setDuelMode] = useState<DuelMode>('live');

  const [phase, setPhase] = useState<DuelPhase>('prep');
  const [prepSecondsLeft, setPrepSecondsLeft] = useState<number>(0);

  const [duelSecondsLeft, setDuelSecondsLeft] = useState<number>(0);
  const duelTimerRef = useRef<number | null>(null);
  const prepTimerRef = useRef<number | null>(null);

  const [myClicks, setMyClicks] = useState<number>(0);

  const [liveSubmitState, setLiveSubmitState] = useState<'idle' | 'waiting' | 'finished'>('idle');
  const livePollRef = useRef<number | null>(null);
  const [finishResponse, setFinishResponse] = useState<any>(null);

  const [challengeAttemptId, setChallengeAttemptId] = useState<number | null>(null);
  const [challengeOpponent, setChallengeOpponent] = useState<any>(null);
  const [challengeFinishResp, setChallengeFinishResp] = useState<any>(null);
  const [challengeAttemptsLeft, setChallengeAttemptsLeft] = useState<number | null>(null);

  const challengeFinishInFlightRef = useRef(false);
  const challengeFinishedRef = useRef(false);

  const [liveOpponent, setLiveOpponent] = useState<any>(null);

  const matchDurationSec = config?.match_duration_sec ?? 30;
  const stakeDefault = config?.stake ?? config?.stake_default ?? 50000;
  const challengeDailyLimit =
    config?.challenge_daily_limit ??
    config?.challenge_limit_per_day ??
    config?.challenge_attempts_per_day ??
    5;

  const autoEndTriggeredRef = useRef(false);
  const duelModeRef = useRef<DuelMode>('live');
  const liveSubmitStateRef = useRef<'idle' | 'waiting' | 'finished'>('idle');
  const challengeAttemptIdRef = useRef<number | null>(null);
  const myClicksRef = useRef<number>(0);

  // telemetry refs
  const sessionStartedAtRef = useRef<number | null>(null);
  const tapTimestampsRef = useRef<number[]>([]);
  const pauseCountRef = useRef<number>(0);
  const longestPauseMsRef = useRef<number>(0);
  const lastTapTsRef = useRef<number | null>(null);
  const maxConcurrentTouchesRef = useRef<number>(1);
  const sendBatchesCountRef = useRef<number>(0);

  useEffect(() => {
    duelModeRef.current = duelMode;
  }, [duelMode]);

  useEffect(() => {
    liveSubmitStateRef.current = liveSubmitState;
  }, [liveSubmitState]);

  useEffect(() => {
    challengeAttemptIdRef.current = challengeAttemptId;
  }, [challengeAttemptId]);

  useEffect(() => {
    myClicksRef.current = myClicks;
  }, [myClicks]);

  useEffect(() => {
  if (screen !== 'duel') return;

  const preventZoom = (e: TouchEvent) => {
    if (e.touches.length > 1) {
      e.preventDefault();
    }
  };

  const preventGesture = (e: Event) => {
    e.preventDefault();
  };

  const preventDoubleTapZoom = (e: TouchEvent) => {
    const now = Date.now();
    const lastTouch = Number((window as any).__lastTouchEnd || 0);

    if (now - lastTouch <= 300) {
      e.preventDefault();
    }

    (window as any).__lastTouchEnd = now;
  };

  document.addEventListener('touchmove', preventZoom, { passive: false });
  document.addEventListener('touchend', preventDoubleTapZoom, { passive: false });

  document.addEventListener('gesturestart', preventGesture, { passive: false } as AddEventListenerOptions);
  document.addEventListener('gesturechange', preventGesture, { passive: false } as AddEventListenerOptions);
  document.addEventListener('gestureend', preventGesture, { passive: false } as AddEventListenerOptions);

  const viewport = document.querySelector('meta[name=viewport]');
  const originalViewport = viewport?.getAttribute('content');

  viewport?.setAttribute(
    'content',
    'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover'
  );

  document.documentElement.style.touchAction = 'none';
  document.body.style.touchAction = 'none';
  document.body.style.overscrollBehavior = 'none';

  return () => {
    document.removeEventListener('touchmove', preventZoom);
    document.removeEventListener('touchend', preventDoubleTapZoom);

    document.removeEventListener('gesturestart', preventGesture);
    document.removeEventListener('gesturechange', preventGesture);
    document.removeEventListener('gestureend', preventGesture);

    if (originalViewport != null) {
      viewport?.setAttribute('content', originalViewport);
    }

    document.documentElement.style.touchAction = '';
    document.body.style.touchAction = '';
    document.body.style.overscrollBehavior = '';
  };
}, [screen]);

  const stopInvitePoll = () => {
    if (invitePollRef.current) {
      window.clearInterval(invitePollRef.current);
      invitePollRef.current = null;
    }
  };

  const stopLivePoll = () => {
    if (livePollRef.current) {
      window.clearInterval(livePollRef.current);
      livePollRef.current = null;
    }
  };

  const stopPrepTimer = () => {
    if (prepTimerRef.current) {
      window.clearInterval(prepTimerRef.current);
      prepTimerRef.current = null;
    }
  };

  const stopDuelTimer = () => {
    if (duelTimerRef.current) {
      window.clearInterval(duelTimerRef.current);
      duelTimerRef.current = null;
    }
  };

  const resetTelemetry = () => {
    sessionStartedAtRef.current = null;
    tapTimestampsRef.current = [];
    pauseCountRef.current = 0;
    longestPauseMsRef.current = 0;
    lastTapTsRef.current = null;
    maxConcurrentTouchesRef.current = 1;
    sendBatchesCountRef.current = 0;
  };

  const buildTelemetryPayload = (): TelemetryPayload => {
    const started = sessionStartedAtRef.current;
    const finished = Date.now();
    const taps = tapTimestampsRef.current.slice().sort((a, b) => a - b);

    const tapCount = taps.length;
    const elapsedSec = started ? Math.max((finished - started) / 1000, 0) : 0;
    const avgTps = elapsedSec > 0 ? tapCount / elapsedSec : tapCount;

    let peakTps = 0;
    for (let i = 0; i < taps.length; i += 1) {
      const windowStart = taps[i];
      let cnt = 0;
      for (let j = i; j < taps.length; j += 1) {
        if (taps[j] - windowStart <= PEAK_WINDOW_MS) cnt += 1;
        else break;
      }
      peakTps = Math.max(peakTps, cnt);
    }

    return {
      client_started_at_ms: started,
      client_finished_at_ms: finished,
      tap_count: tapCount,
      max_concurrent_touches: Math.max(1, maxConcurrentTouchesRef.current),
      avg_taps_per_sec: Number(avgTps.toFixed(2)),
      peak_taps_per_sec: Number(peakTps.toFixed(2)),
      send_batches_count: Math.max(1, sendBatchesCountRef.current),
      had_pauses: pauseCountRef.current > 0,
      pause_count: pauseCountRef.current,
      longest_pause_ms: longestPauseMsRef.current,
    };
  };

  const setUserFriendlyError = (e: any) => {
    const parsed = parseServerError(e);

    if (parsed?.code === 'ATTEMPT_NOT_ACTIVE' && String(parsed?.message || '').toLowerCase().includes('finished')) {
      setError('');
      return;
    }

    setError(t('pvp_error_generic', { defaultValue: 'Bir xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.' }));
  };

  const refreshMe = async () => {
    if (!telegramId) return;
    try {
      const me = await apiRequest<any>(`/api/pvp/me?telegram_id=${telegramId}`);
      if (me?.user_id) setMeUserId(me.user_id);
      setMeInfo(me);

      const left = pickChallengeAttemptsLeft(me);
      if (left != null) setChallengeAttemptsLeft(left);
    } catch {
      // ignore
    }
  };

  const refreshWeekly = async () => {
    setWeeklyLoading(true);
    try {
      let season: any = null;
      try {
        const cur = await apiRequest<any>('/api/pvp/weekly-season/current');
        season = cur?.season ?? null;
      } catch {
        season = null;
      }

      try {
        const lb = await apiRequest<any>('/api/pvp/weekly-season/leaderboard?limit=10');
        setWeeklySeason(lb?.season ?? season);
        setWeeklyItems(Array.isArray(lb?.items) ? lb.items : []);
        return;
      } catch {}

      const legacy = await apiRequest<any>('/api/pvp/leaderboard');
      setWeeklySeason(season);
      setWeeklyItems(Array.isArray(legacy?.items) ? legacy.items : []);
    } catch {
      setWeeklyItems([]);
    } finally {
      setWeeklyLoading(false);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const cfg = await apiRequest<any>('/api/pvp/config');
        setConfig(cfg);
      } catch {}
    })();

    return () => {
      stopPrepTimer();
      stopDuelTimer();
      stopInvitePoll();
      stopLivePoll();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refreshMe();
    refreshWeekly();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [telegramId]);

  const computeOpponentUserId = (): number | null => {
    if (matchInfo?.opponent_user_id) return matchInfo.opponent_user_id;

    if (!meUserId || !matchInfo) return null;
    const p1 = matchInfo.player1_id;
    const p2 = matchInfo.player2_id;
    if (typeof p1 !== 'number' || typeof p2 !== 'number') return null;
    if (p1 === meUserId) return p2;
    if (p2 === meUserId) return p1;
    return null;
  };

  const fetchPublicUser = async (userId: number) => {
    const candidates = [
      `/api/pvp/user/public?user_id=${userId}`,
      `/api/pvp/user?user_id=${userId}`,
      `/api/user/public?user_id=${userId}`,
      `/api/user/get?user_id=${userId}`,
    ];

    for (const path of candidates) {
      try {
        const u = await apiRequest<any>(path);
        return u?.user ?? u;
      } catch {}
    }
    return null;
  };

  useEffect(() => {
    (async () => {
      if (duelMode !== 'live') return;

      const embedded = getEmbeddedLiveOpponent(matchInfo, meUserId);
      if (embedded) {
        setLiveOpponent(embedded);
        return;
      }

      const oppId = computeOpponentUserId();
      if (!oppId) {
        setLiveOpponent(null);
        return;
      }

      const u = await fetchPublicUser(oppId);
      setLiveOpponent(u);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchInfo, duelMode, meUserId]);

  const pollLiveStatus = (matchToken: string) => {
    stopLivePoll();
    livePollRef.current = window.setInterval(async () => {
      if (!telegramId) return;
      try {
        const st = await apiRequest<any>(
          `/api/pvp/live/status?telegram_id=${telegramId}&match_token=${encodeURIComponent(matchToken)}`
        );

        if (st?.opponent) setLiveOpponent(st.opponent);

        if (st?.status === 'finished' && (st?.result || st?.match_id)) {
          setLiveSubmitState('finished');

          const merged =
            st?.result
              ? {
                  ...st.result,
                  status: st.status,
                  anti_cheat: st.anti_cheat ?? null,
                  player1: st.player1 ?? st.result?.player1 ?? null,
                  player2: st.player2 ?? st.result?.player2 ?? null,
                  opponent: st.opponent ?? null,
                  match_token: st.match_token,
                }
              : st;

          setFinishResponse(merged);
          stopLivePoll();
          await refreshMe();
          await refreshWeekly();
        }

        if (st?.status === 'expired') {
          setError(t('pvp_error_generic', { defaultValue: 'Bir xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.' }));
          stopLivePoll();
        }
      } catch {
        // ignore
      }
    }, 900);
  };

  const onLiveSubmit = async () => {
    if (!telegramId) return;
    const token = matchInfo?.match_token;
    if (!token) {
      setUserFriendlyError(new Error('match_token missing'));
      return;
    }

    if (liveSubmitStateRef.current !== 'idle') return;

    setError('');
    setLoading(true);
    try {
      sendBatchesCountRef.current += 1;

      const telemetry = buildTelemetryPayload();

      const res = await apiRequest<any>('/api/pvp/live/submit', {
        method: 'POST',
        body: JSON.stringify({
          telegram_id: telegramId,
          match_token: token,
          my_clicks: myClicksRef.current,
          telemetry,
        }),
      });

      if (res?.player1 || res?.player2 || res?.opponent) {
        setMatchInfo((prev: any) => ({ ...(prev || {}), ...res }));
      }

      if (res?.status === 'finished') {
        setLiveSubmitState('finished');
        setFinishResponse(res);
        await refreshMe();
        await refreshWeekly();
      } else {
        setLiveSubmitState('waiting');
        if (res?.player1 || res?.player2 || res?.opponent) {
          setMatchInfo((prev: any) => ({ ...(prev || {}), ...res }));
        }
        pollLiveStatus(token);
      }
    } catch (e: any) {
      const parsed = parseServerError(e);
      const msg = String(parsed?.message || '').toLowerCase();
      const code = String(parsed?.code || '').toUpperCase();

      const shouldPoll =
        msg.includes('already') ||
        msg.includes('submitted') ||
        msg.includes('finished') ||
        msg.includes('not active') ||
        code.includes('ALREADY') ||
        code.includes('FINISHED') ||
        code.includes('NOT_ACTIVE');

      if (shouldPoll) {
        setError('');
        setLiveSubmitState('waiting');
        pollLiveStatus(token);
      } else {
        setLiveSubmitState('waiting');
        pollLiveStatus(token);
        setUserFriendlyError(e);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (screen !== 'result') return;

    if (duelModeRef.current === 'challenge') {
      if (!challengeFinishedRef.current && !challengeFinishInFlightRef.current && challengeAttemptIdRef.current) {
        void onChallengeFinish();
      }
      return;
    }

    if (liveSubmitStateRef.current === 'idle' && matchInfo?.match_token) {
      void onLiveSubmit();
    } else if (liveSubmitStateRef.current === 'waiting' && matchInfo?.match_token) {
      pollLiveStatus(matchInfo.match_token);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen]);

  const onChallengeFinish = async () => {
    if (!telegramId) return;

    if (challengeFinishedRef.current) return;
    if (challengeFinishInFlightRef.current) return;

    const attemptId = challengeAttemptIdRef.current;
    if (!attemptId) {
      setUserFriendlyError(new Error('attempt_id missing'));
      return;
    }

    challengeFinishInFlightRef.current = true;
    setError('');
    setLoading(true);

    try {
      sendBatchesCountRef.current += 1;

      const telemetry = buildTelemetryPayload();

      const res = await apiRequest<any>('/api/pvp/challenge/finish', {
        method: 'POST',
        body: JSON.stringify({
          telegram_id: telegramId,
          attempt_id: attemptId,
          my_clicks: myClicksRef.current,
          telemetry,
        }),
      });

      challengeFinishedRef.current = true;
      setChallengeFinishResp(res);

      const left = pickChallengeAttemptsLeft(res);
      if (left != null) setChallengeAttemptsLeft(left);

      if (res?.opponent) setChallengeOpponent(res.opponent);

      await refreshMe();
      await refreshWeekly();
    } catch (e: any) {
      const parsed = parseServerError(e);
      if (parsed?.code === 'ATTEMPT_NOT_ACTIVE' && String(parsed?.message || '').toLowerCase().includes('finished')) {
        challengeFinishedRef.current = true;
        setError('');
        await refreshMe();
        await refreshWeekly();
      } else {
        setUserFriendlyError(e);
      }
    } finally {
      challengeFinishInFlightRef.current = false;
      setLoading(false);
    }
  };

  const triggerAutoEndIfNeeded = () => {
    if (autoEndTriggeredRef.current) return;
    autoEndTriggeredRef.current = true;

    setScreen('result');

    if (duelModeRef.current === 'challenge') {
      void onChallengeFinish();
      return;
    }
    void onLiveSubmit();
  };

  const startActiveTimer = () => {
    stopDuelTimer();
    sessionStartedAtRef.current = Date.now();

    const startedAt = Date.now();
    duelTimerRef.current = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      const left = Math.max(0, matchDurationSec - elapsed);
      setDuelSecondsLeft(left);

      if (left <= 0) {
        stopDuelTimer();
        triggerAutoEndIfNeeded();
      }
    }, 200);
  };

  const startPrepCountdown = () => {
    stopPrepTimer();
    setPhase('prep');
    setPrepSecondsLeft(PREP_SECONDS);

    const startedAt = Date.now();
    prepTimerRef.current = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      const left = Math.max(0, PREP_SECONDS - elapsed);
      setPrepSecondsLeft(left);

      if (left <= 0) {
        stopPrepTimer();
        setPhase('active');
        startActiveTimer();
      }
    }, 150);
  };

  const startDuel = (mode: DuelMode) => {
    setError('');
    setFinishResponse(null);
    setChallengeFinishResp(null);

    challengeFinishInFlightRef.current = false;
    challengeFinishedRef.current = false;

    resetTelemetry();

    setMyClicks(0);
    setLiveSubmitState('idle');
    stopLivePoll();

    autoEndTriggeredRef.current = false;

    stopPrepTimer();
    stopDuelTimer();
    setPhase('prep');
    setPrepSecondsLeft(PREP_SECONDS);

    setDuelMode(mode);
    setDuelSecondsLeft(matchDurationSec);
    setScreen('duel');

    startPrepCountdown();
  };

  const autoAcceptRef = useRef<string | null>(null);
  useEffect(() => {
    const sp = (WebApp.initDataUnsafe as any)?.start_param;
    if (!telegramId) return;
    if (!sp || typeof sp !== 'string') return;
    if (!sp.startsWith('pvp_')) return;

    const code = sp.replace('pvp_', '').trim();
    if (!code) return;

    if (autoAcceptRef.current === code) return;
    autoAcceptRef.current = code;

    (async () => {
      setError('');
      setLoading(true);
      try {
        const data = await apiRequest<any>('/api/pvp/invite/accept', {
          method: 'POST',
          body: JSON.stringify({ telegram_id: telegramId, invite_code: code }),
        });

        setMatchInfo(data);
        if (data?.player1 || data?.player2 || data?.opponent) {
          setLiveOpponent(getEmbeddedLiveOpponent(data, meUserId));
        }

        if (data?.match_token) startDuel('live');
      } catch (e: any) {
        setUserFriendlyError(e);
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [telegramId]);

  const [glow, setGlow] = useState<number>(0);
  const recentClicksRef = useRef<Array<{ ts: number; delta: number }>>([]);
  const glowTickRef = useRef<number | null>(null);

  const computeGlow = () => {
    const now = Date.now();
    const arr = recentClicksRef.current.filter((x) => now - x.ts <= GLOW_WINDOW_MS);
    recentClicksRef.current = arr;

    const sum = arr.reduce((acc, x) => acc + x.delta, 0);
    const cps = (sum / GLOW_WINDOW_MS) * 1000;
    const intensity = Math.max(0, Math.min(1, cps / GLOW_MAX_CPS));

    setGlow((prev) => {
      if (intensity <= prev) return prev;
      return prev + (intensity - prev) * GLOW_RISE_LERP;
    });
  };

  useEffect(() => {
    if (glowTickRef.current) window.clearInterval(glowTickRef.current);
    glowTickRef.current = window.setInterval(() => {
      setGlow((prev) => Math.max(0, prev - GLOW_DECAY_PER_TICK));
    }, GLOW_TICK_MS);

    return () => {
      if (glowTickRef.current) {
        window.clearInterval(glowTickRef.current);
        glowTickRef.current = null;
      }
    };
  }, []);

  const registerTapBatch = (batchSize: number) => {
    const now = Date.now();
    for (let i = 0; i < batchSize; i += 1) {
      tapTimestampsRef.current.push(now);
    }

    if (lastTapTsRef.current != null) {
      const gap = now - lastTapTsRef.current;
      if (gap >= PAUSE_THRESHOLD_MS) {
        pauseCountRef.current += 1;
        longestPauseMsRef.current = Math.max(longestPauseMsRef.current, gap);
      }
    }
    lastTapTsRef.current = now;
  };

  const addClicks = (delta: number) => {
    if (screen !== 'duel') return;
    if (phase !== 'active') return;
    if (duelSecondsLeft <= 0) return;

    const d = Math.max(0, delta);
    setMyClicks((prev) => prev + d);

    registerTapBatch(d);

    recentClicksRef.current.push({ ts: Date.now(), delta: d });
    computeGlow();
  };

const lastTouchAtRef = useRef<number>(0);

const onTouchStart = (e: React.TouchEvent<HTMLButtonElement>) => {
  e.preventDefault();

  if (screen !== 'duel') return;
  if (phase !== 'active') return;
  if (duelSecondsLeft <= 0) return;

  lastTouchAtRef.current = Date.now();

  const changed = e.changedTouches?.length || 1;
  const activeNow = e.touches?.length || changed;

  const accepted = Math.min(changed, 2);

  maxConcurrentTouchesRef.current = Math.max(
    maxConcurrentTouchesRef.current,
    Math.min(activeNow, 2)
  );

  if (accepted > 0) addClicks(accepted);
};

const onMouseDown = (e: React.MouseEvent<HTMLButtonElement>) => {
  e.preventDefault();

  if (Date.now() - lastTouchAtRef.current < 700) return;

  maxConcurrentTouchesRef.current = Math.max(maxConcurrentTouchesRef.current, 1);
  addClicks(1);
};

  const startInvitePolling = (code: string) => {
    stopInvitePoll();
    invitePollRef.current = window.setInterval(async () => {
      try {
        const st = await apiRequest<any>(`/api/pvp/invite/status?invite_code=${encodeURIComponent(code)}`);

        if (st?.status === 'accepted' && st?.match_token) {
          const mi = {
            ok: true,
            match_token: st.match_token,
            stake: st.stake ?? stakeDefault,
            match_duration_sec: st.match_duration_sec ?? matchDurationSec,
            mode: 'invite',
            player1_id: st.player1_id,
            player2_id: st.player2_id,
            player1: st.player1 ?? null,
            player2: st.player2 ?? null,
            opponent: st.opponent ?? null,
          };
          setMatchInfo(mi);
          stopInvitePoll();
          startDuel('live');
        }

        if (st?.status === 'expired' || st?.status === 'cancelled') stopInvitePoll();
      } catch {
        // ignore
      }
    }, 800);
  };

  const onCreateInvite = async () => {
    if (!telegramId) return;
    setError('');
    setLoading(true);
    try {
      const data = await apiRequest<any>('/api/pvp/invite/create', {
        method: 'POST',
        body: JSON.stringify({ telegram_id: telegramId, ttl_seconds: 3600 }),
      });
      setCreatedInvite(data);
      if (data?.invite_code) startInvitePolling(data.invite_code);
    } catch (e: any) {
      setUserFriendlyError(e);
    } finally {
      setLoading(false);
    }
  };

  const onCancelInvite = async () => {
    if (!telegramId) return;
    const code = createdInvite?.invite_code;
    if (!code) return;

    setError('');
    setLoading(true);
    try {
      await apiRequest<any>('/api/pvp/invite/cancel', {
        method: 'POST',
        body: JSON.stringify({ telegram_id: telegramId, invite_code: code }),
      });
      stopInvitePoll();
      setCreatedInvite(null);
    } catch (e: any) {
      setUserFriendlyError(e);
    } finally {
      setLoading(false);
    }
  };

  const copyText = async (txt: string) => {
    try {
      await navigator.clipboard.writeText(txt);
      WebApp.showToast?.(t('copied', { defaultValue: 'Kopyalandı' }));
    } catch {}
  };

  const shareInvite = (code: string) => {
    const url = buildInviteLink(code);
    const text = t('pvp_invite_share_text', { defaultValue: '⚔️ Gappick-də duelə qoşul! Bu linki aç:' });
    const tgShare = buildShareLink(url, text);

    try {
      (WebApp as any).openTelegramLink?.(tgShare);
    } catch {
      window.open(tgShare, '_blank');
    }
  };

  const onChallengeStart = async () => {
    if (!telegramId) return;
    setError('');
    setLoading(true);
    try {
      const res = await apiRequest<any>('/api/pvp/challenge/start', {
        method: 'POST',
        body: JSON.stringify({ telegram_id: telegramId }),
      });

      setChallengeAttemptId(res?.attempt_id ?? null);
      setChallengeOpponent(res?.opponent ?? null);

      const left = pickChallengeAttemptsLeft(res);
      if (left != null) setChallengeAttemptsLeft(left);

      startDuel('challenge');
    } catch (e: any) {
      setUserFriendlyError(e);
    } finally {
      setLoading(false);
    }
  };

  const resetToLobby = () => {
    stopPrepTimer();
    stopDuelTimer();
    stopLivePoll();

    setScreen('lobby');
    setMyClicks(0);
    setFinishResponse(null);
    setLiveSubmitState('idle');

    setChallengeFinishResp(null);
    setChallengeAttemptId(null);
    setChallengeOpponent(null);

    setPhase('prep');
    setPrepSecondsLeft(0);
    setDuelSecondsLeft(0);

    autoEndTriggeredRef.current = false;
    setGlow(0);
    recentClicksRef.current = [];

    challengeFinishInFlightRef.current = false;
    challengeFinishedRef.current = false;

    resetTelemetry();

    setError('');
    void refreshMe();
    void refreshWeekly();
  };

  const isChallenge = duelMode === 'challenge';
  const victories = pickVictories(meInfo);
  const best = pickBest(meInfo);

  const challengeLeft = challengeAttemptsLeft ?? pickChallengeAttemptsLeft(meInfo) ?? pickChallengeAttemptsLeft(challengeFinishResp);

  const opponentUserId = computeOpponentUserId();
  const inviteUrl = createdInvite?.invite_code ? buildInviteLink(createdInvite.invite_code) : '';

  const duelOpponentLabel = isChallenge
    ? formatUserLabel(challengeOpponent, challengeOpponent?.user_id ?? null)
    : formatUserLabel(liveOpponent, opponentUserId);

  const opponentBest = isChallenge ? intOrZero(challengeOpponent?.best_result ?? challengeOpponent?.pvp_best_result) : null;

  const bubbleGlowStyle: React.CSSProperties = {
    background:
      `radial-gradient(circle at 50% 45%, ` +
      `rgba(0,240,255,${0.14 + 0.35 * glow}) 0%, ` +
      `rgba(0,240,255,${0.06 + 0.22 * glow}) 35%, ` +
      `rgba(0,240,255,0) 72%)`,
    boxShadow:
      `0 0 ${18 + 55 * glow}px rgba(0,240,255,${0.18 + 0.55 * glow}), ` +
      `0 0 ${10 + 34 * glow}px rgba(255,215,0,${0.06 + 0.18 * glow})`,
  };

  const rawResult = duelMode === 'challenge' ? challengeFinishResp : finishResponse;
  const outcome: Outcome = normalizeOutcome(rawResult, meUserId);

  const liveResolvedClicks = !isChallenge ? resolveLiveClicks(rawResult, meUserId) : null;
  const liveVerdicts = !isChallenge ? getLiveVerdicts(rawResult, meUserId) : { me: null, opponent: null };
  const challengeVerdict = isChallenge ? getChallengeVerdict(rawResult) : null;

  const myValidatedClicks =
    isChallenge
      ? extractNumber(challengeVerdict, ['validated_clicks'])
      : extractNumber(liveVerdicts.me, ['validated_clicks']);

  const myReportedClicks =
    isChallenge
      ? extractNumber(challengeVerdict, ['reported_clicks'])
      : extractNumber(liveVerdicts.me, ['reported_clicks']);

  const oppValidatedClicks =
    !isChallenge
      ? extractNumber(liveVerdicts.opponent, ['validated_clicks'])
      : null;

  const myClicksFromResult =
    isChallenge
      ? extractNumber(rawResult, ['challenger_clicks', 'my_clicks', 'your_clicks', 'clicks', 'myClicks', 'yourClicks']) ??
        myValidatedClicks ??
        myClicks
      : liveResolvedClicks?.myClicks ?? myValidatedClicks ?? myClicks;

  const oppClicksFromResult =
    isChallenge
      ? extractNumber(rawResult, ['opponent_best_result', 'opponent_clicks', 'enemy_clicks', 'their_clicks']) ??
        opponentBest
      : liveResolvedClicks?.opponentClicks ?? oppValidatedClicks;

  const deltaCoins =
    extractNumber(rawResult, ['delta_coins', 'deltaCoins', 'reward_delta', 'rewardDelta', 'coins_delta']) ??
    extractNumber(rawResult?.result, ['delta_coins', 'deltaCoins', 'reward_delta', 'rewardDelta', 'coins_delta']);

  const rewardCoins =
    extractNumber(rawResult, ['reward_coins', 'rewardCoins', 'reward', 'win_reward', 'winReward']) ??
    extractNumber(rawResult?.result, ['reward_coins', 'rewardCoins', 'reward', 'win_reward', 'winReward']);

  const stakeValue =
    extractNumber(rawResult, ['stake', 'stake_value', 'stakeValue']) ??
    extractNumber(rawResult?.result, ['stake', 'stake_value', 'stakeValue']) ??
    stakeDefault;

  const potValue =
    extractNumber(rawResult, ['pot', 'bank', 'pool', 'potValue']) ??
    extractNumber(rawResult?.result, ['pot', 'bank', 'pool', 'potValue']);

  const mySuspicious = isChallenge
    ? Boolean(challengeVerdict?.is_suspicious)
    : Boolean(liveVerdicts.me?.is_suspicious);

  const opponentSuspicious = !isChallenge ? Boolean(liveVerdicts.opponent?.is_suspicious) : false;

  const myVerdictReason = isChallenge ? challengeVerdict?.reason : liveVerdicts.me?.reason;
  const opponentVerdictReason = !isChallenge ? liveVerdicts.opponent?.reason : null;

  const outcomeTitle =
    mySuspicious
      ? t('pvp_outcome_invalidated', { defaultValue: 'Nəticə ləğv edildi' })
      : outcome === 'win'
      ? t('pvp_outcome_win', { defaultValue: 'Qələbə 🎉' })
      : outcome === 'lose'
      ? t('pvp_outcome_lose', { defaultValue: 'Məğlubiyyət' })
      : outcome === 'draw'
      ? t('pvp_outcome_draw', { defaultValue: 'Heç-heçə' })
      : t('pvp_outcome_unknown', { defaultValue: '—' });

  const outcomeBadge =
    mySuspicious
      ? 'bg-rose-500/15 border-rose-400/30 text-rose-200'
      : outcome === 'win'
      ? 'bg-emerald-500/15 border-emerald-400/30 text-emerald-200'
      : outcome === 'lose'
      ? 'bg-rose-500/15 border-rose-400/30 text-rose-200'
      : outcome === 'draw'
      ? 'bg-amber-500/15 border-amber-400/30 text-amber-200'
      : 'bg-white/5 border-white/10 text-white/80';

  const rewardLine = (() => {
    if (mySuspicious) {
      return t('pvp_reward_invalidated', { defaultValue: 'Nəticə suspicious telemetry səbəbilə nəzərə alınmadı' });
    }
    if (rewardCoins != null) return `+${intOrZero(rewardCoins)} $GAP`;
    if (deltaCoins != null) return `${deltaCoins >= 0 ? '+' : ''}${intOrZero(deltaCoins)} $GAP`;
    const maybe =
      extractNumber(rawResult, ['delta', 'change', 'balance_change']) ??
      extractNumber(rawResult?.result, ['delta', 'change', 'balance_change']);
    if (maybe != null) return `${maybe >= 0 ? '+' : ''}${intOrZero(maybe)} $GAP`;
    return t('pvp_reward_unknown', { defaultValue: '—' });
  })();

  const renderErrorBanner = () => {
    if (!error) return null;
    return (
      <div className="mt-3 rounded-2xl bg-rose-500/10 border border-rose-400/20 p-3 text-xs text-rose-100">
        {error}
      </div>
    );
  };

  const renderAntiCheatBanner = () => {
    if (screen !== 'result') return null;
    if (!mySuspicious && !opponentSuspicious) return null;

    return (
      <div className="mt-4 rounded-2xl bg-amber-500/10 border border-amber-400/25 p-4 text-xs text-amber-100">
        <div className="font-semibold text-sm">
          {t('pvp_fairplay_notice', { defaultValue: 'Fair Play yoxlaması' })}
        </div>

        {mySuspicious ? (
          <div className="mt-2">
            {t('pvp_me_flagged', {
              defaultValue: 'Sənin nəticən suspicious kimi işarələndi və qələbə hesablanmadı.',
            })}
            {myVerdictReason ? (
              <div className="mt-1 opacity-80">
                {t('pvp_reason', { defaultValue: 'Səbəb' })}: <span className="font-mono">{myVerdictReason}</span>
              </div>
            ) : null}
          </div>
        ) : null}

        {!mySuspicious && opponentSuspicious ? (
          <div className="mt-2">
            {t('pvp_opponent_flagged', {
              defaultValue: 'Rəqibin nəticəsi suspicious kimi işarələndi və validasiya olundu.',
            })}
            {opponentVerdictReason ? (
              <div className="mt-1 opacity-80">
                {t('pvp_reason', { defaultValue: 'Səbəb' })}: <span className="font-mono">{opponentVerdictReason}</span>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  };

  const renderLobbyHeader = () => (
    <>
      <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4 shadow-[0_0_12px_#00f0ff20]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-base font-bold">⚔️ PvP</div>
            <div className="text-xs opacity-80">{t('pvp_subtitle', { defaultValue: 'Live duel & Challenge' })}</div>
          </div>

          <button
            className="rounded-xl bg-white/10 border border-white/10 px-3 py-2 text-xs"
            onClick={() => {
              setError('');
              void refreshMe();
              void refreshWeekly();
            }}
            disabled={loading}
          >
            {t('refresh', { defaultValue: 'Yenilə' })}
          </button>
        </div>

        {meInfo ? (
          <div className="mt-3 text-xs opacity-90">
            <div className="opacity-80">
              {t('pvp_you', {
                id: meInfo.user_id || meUserId || '—',
                username: meInfo.username || '—',
                defaultValue: 'you: #{{id}} @{{username}}',
              })}
            </div>
            <div>{t('pvp_stats', { v: victories, b: best, defaultValue: 'qələbə: {{v}} | best: {{b}}' })}</div>
          </div>
        ) : (
          <div className="mt-3 text-xs opacity-70">{t('loading', { defaultValue: 'Yüklənir…' })}</div>
        )}

        {renderErrorBanner()}
      </div>

      <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4 shadow-[0_0_12px_#00f0ff20]">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">🏆 {t('pvp_weekly_leaderboard', { defaultValue: 'Weekly leaderboard' })}</div>
          <button
            className="text-xs opacity-80 underline underline-offset-2 disabled:opacity-50"
            onClick={refreshWeekly}
            disabled={weeklyLoading}
          >
            {weeklyLoading ? t('loading', { defaultValue: 'Yüklənir…' }) : t('refresh', { defaultValue: 'Yenilə' })}
          </button>
        </div>

        {weeklySeason?.season_no != null && (
          <div className="mt-2 text-xs opacity-75">
            {t('pvp_season', { defaultValue: 'Sezon:' })}{' '}
            <span className="font-mono">{weeklySeason.season_no}</span>
            {weeklySeason?.end_at ? (
              <>
                {' '}
                • {t('pvp_time_left', { defaultValue: 'Bitmə vaxtı' })}:{' '}
                <span className="font-mono">{new Date(weeklySeason.end_at).toLocaleString()}</span>
              </>
            ) : null}
          </div>
        )}

        {weeklyItems.length === 0 ? (
          <div className="mt-3 text-xs opacity-70">{t('pvp_no_leaderboard', { defaultValue: 'Hələlik məlumat yoxdur.' })}</div>
        ) : (
          <div className="mt-3 overflow-hidden rounded-xl border border-white/10">
            <table className="w-full text-left text-xs">
              <thead className="bg-white/5">
                <tr>
                  <th className="px-3 py-2 w-10">#</th>
                  <th className="px-3 py-2">{t('player', { defaultValue: 'Oyunçu' })}</th>
                  <th className="px-3 py-2 w-24 text-right">{t('victories', { defaultValue: 'Qələbə' })}</th>
                  <th className="px-3 py-2 w-24 text-right">{t('best', { defaultValue: 'Rekord' })}</th>
                </tr>
              </thead>
              <tbody>
                {weeklyItems.map((u: any, idx: number) => {
                  const isMe = meInfo?.user_id && u?.user_id === meInfo.user_id;
                  const name = u?.username
                    ? `@${u.username}`
                    : u?.first_name || u?.last_name
                    ? `${u.first_name || ''} ${u.last_name || ''}`.trim()
                    : `#${u?.user_id ?? '—'}`;

                  return (
                    <tr key={u?.user_id ?? idx} className={isMe ? 'bg-white/10' : 'bg-transparent'}>
                      <td className="px-3 py-2">{u?.rank ?? idx + 1}</td>
                      <td className="px-3 py-2">{name}</td>
                      <td className="px-3 py-2 text-right">{intOrZero(u?.victories)}</td>
                      <td className="px-3 py-2 text-right">{intOrZero(u?.best_result)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );

  const renderDuelHeader = () => (
    <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4 shadow-[0_0_12px_#00f0ff20]">
      <div className="flex items-center justify-between">
        <button className="rounded-xl bg-white/10 border border-white/10 px-3 py-2 text-sm" onClick={resetToLobby}>
          ← {t('back', { defaultValue: 'Geri' })}
        </button>

        <div className="text-center">
          <div className="text-sm font-semibold">
            {isChallenge ? t('pvp_challenge_title', { defaultValue: 'Challenge' }) : t('pvp_duel', { defaultValue: 'Duel' })}
          </div>
          <div className="text-[11px] opacity-80">
            {t('pvp_vs', { defaultValue: 'vs' })}{' '}
            <span className="font-semibold">{duelOpponentLabel}</span>
            {isChallenge && opponentBest != null ? (
              <span className="opacity-80">
                {' '}
                • {t('pvp_best_label', { defaultValue: 'best' })}:{' '}
                <span className="font-mono">{opponentBest}</span>
              </span>
            ) : null}
          </div>
          <div className="text-[11px] opacity-75">
            {phase === 'prep' ? t('pvp_get_ready', { defaultValue: 'Hazır ol' }) : t('pvp_go', { defaultValue: 'Başla!' })}
          </div>
        </div>

        <div className="text-right">
          <div className="text-[11px] opacity-75">{t('time', { defaultValue: 'vaxt' })}</div>
          <div className="text-xl font-extrabold">{phase === 'prep' ? `${prepSecondsLeft}` : `${duelSecondsLeft}`}</div>
        </div>
      </div>

      {renderErrorBanner()}
    </div>
  );

  const renderContent = () => {
    if (screen === 'duel') {
      return (
        <div className="mt-4">
          {renderDuelHeader()}

          <div className="mt-4 grid grid-cols-3 gap-3">
            <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff20] p-3 text-center">
              <div className="text-[11px] opacity-70">{t('pvp_your_clicks', { defaultValue: 'Klik' })}</div>
              <div className="text-2xl font-extrabold">{myClicks}</div>
            </div>

            <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff20] p-3 text-center">
              <div className="text-[11px] opacity-70">{t('pvp_opponent', { defaultValue: 'Rəqib' })}</div>
              <div className="text-sm font-semibold truncate">{duelOpponentLabel}</div>
            </div>

            <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff20] p-3 text-center">
              <div className="text-[11px] opacity-70">{t('pvp_power', { defaultValue: 'Güc' })}</div>
              <div className="text-2xl font-extrabold">{Math.round(glow * 100)}%</div>
            </div>
          </div>

          <div className="mt-6 flex items-center justify-center">
            <div className="relative">
              <button
                className="relative rounded-full border border-[#00f0ff50] bg-[#0b1320] active:scale-[0.99] transition-transform"
                onTouchStart={onTouchStart}
                onMouseDown={onMouseDown}
                style={{
                  width: 260,
                  height: 260,
                  touchAction: 'manipulation',
                  userSelect: 'none',
                  WebkitUserSelect: 'none',
                  WebkitTouchCallout: 'none',
                  boxShadow: '0 0 14px rgba(0,240,255,0.12)',
                }}
              >
                <div className="absolute inset-0 rounded-full" style={bubbleGlowStyle} />

                <div
                  className="absolute inset-0 rounded-full"
                  style={{
                    background:
                      'radial-gradient(circle at 35% 30%, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0.03) 35%, rgba(255,255,255,0) 70%)',
                  }}
                />

                <div className="relative z-10 flex h-full w-full flex-col items-center justify-center">
                  <div className="text-[12px] opacity-75">
                    {phase === 'prep'
                      ? t('pvp_wait_start', { defaultValue: 'Hazırlaş…' })
                      : t('pvp_tap', { defaultValue: 'Toxun' })}
                  </div>

                  <div className="mt-1 text-4xl font-extrabold">+1</div>

                  {phase === 'prep' ? (
                    <div className="mt-3 rounded-xl bg-black/40 border border-white/10 px-4 py-2">
                      <div className="text-[11px] opacity-80">{t('pvp_starts_in', { defaultValue: 'Start:' })}</div>
                      <div className="text-2xl font-bold">{prepSecondsLeft}</div>
                    </div>
                  ) : (
                    <div className="mt-3 text-[11px] opacity-70">
                      {t('pvp_speed_hint', { defaultValue: 'Sürət artdıqca effekt güclənir' })}
                    </div>
                  )}
                </div>
              </button>

              {phase === 'active' && duelSecondsLeft <= 0 ? (
                <div className="mt-4 text-center text-xs opacity-80">
                  {t('pvp_finishing', { defaultValue: 'Nəticə hesablanır…' })}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      );
    }

    if (screen === 'result') {
      const waitingServer =
        duelMode === 'challenge'
          ? !challengeFinishResp && !challengeFinishedRef.current && !error
          : liveSubmitState !== 'finished' && !finishResponse && !error;

      return (
        <div className="mt-4">
          {renderDuelHeader()}

          <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff20] p-4">
            <div className="flex items-center justify-between">
              <div className="text-base font-bold">🏁 {t('pvp_result', { defaultValue: 'Nəticə' })}</div>
              <div className={`px-3 py-1 rounded-xl border text-xs ${outcomeBadge}`}>{outcomeTitle}</div>
            </div>

            {waitingServer ? (
              <div className="mt-4 rounded-2xl bg-[#0b1320] border border-white/10 p-4 text-center">
                <div className="text-sm font-semibold">{t('loading', { defaultValue: 'Yüklənir…' })}</div>
                <div className="mt-1 text-xs opacity-75">{t('pvp_finishing', { defaultValue: 'Nəticə hesablanır…' })}</div>
              </div>
            ) : (
              <>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-2xl bg-[#0b1320] border border-[#00f0ff20] p-3">
                    <div className="text-[11px] opacity-70">{t('pvp_you_label', { defaultValue: 'Sən' })}</div>
                    <div className="mt-1 text-sm font-semibold">{formatUserLabel(meInfo, meUserId)}</div>
                    <div className="mt-2 text-[11px] opacity-70">{t('pvp_clicks', { defaultValue: 'Kliklər' })}</div>
                    <div className="text-2xl font-extrabold">{myClicksFromResult}</div>

                    {(myReportedClicks != null || myValidatedClicks != null) && (
                      <div className="mt-2 text-[11px] opacity-75">
                        raw: <span className="font-mono">{myReportedClicks ?? '—'}</span>
                        {' • '}
                        valid: <span className="font-mono">{myValidatedClicks ?? '—'}</span>
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl bg-[#0b1320] border border-[#00f0ff20] p-3">
                    <div className="text-[11px] opacity-70">{t('pvp_opponent', { defaultValue: 'Rəqib' })}</div>
                    <div className="mt-1 text-sm font-semibold truncate">{duelOpponentLabel}</div>
                    <div className="mt-2 text-[11px] opacity-70">
                      {isChallenge
                        ? t('pvp_target', { defaultValue: 'Hədəf nəticə' })
                        : t('pvp_clicks', { defaultValue: 'Kliklər' })}
                    </div>
                    <div className="text-2xl font-extrabold">{oppClicksFromResult ?? '—'}</div>

                    {!isChallenge && oppValidatedClicks != null && (
                      <div className="mt-2 text-[11px] opacity-75">
                        valid: <span className="font-mono">{oppValidatedClicks}</span>
                      </div>
                    )}
                  </div>
                </div>

                {renderAntiCheatBanner()}

                <div className="mt-4 rounded-2xl bg-[#0b1320] border border-white/10 p-3">
                  <div className="text-[11px] opacity-70">{t('pvp_reward', { defaultValue: 'Mükafat / dəyişiklik' })}</div>
                  <div className="mt-1 text-lg font-bold">{rewardLine}</div>

                  {!isChallenge ? (
                    <div className="mt-1 text-[11px] opacity-70">
                      {t('pvp_stake', { defaultValue: 'stake:' })} <span className="font-mono">{stakeValue}</span>
                      {potValue != null ? (
                        <>
                          {' '}
                          • {t('pvp_pot', { defaultValue: 'pot:' })} <span className="font-mono">{potValue}</span>
                        </>
                      ) : null}
                    </div>
                  ) : (
                    <div className="mt-1 text-[11px] opacity-70">
                      {t('pvp_challenge_rules_hint', { defaultValue: 'Challenge: qələbə +1 victory, məğlubiyyət +0. Stake yoxdur.' })}
                    </div>
                  )}
                </div>

                {(mySuspicious || opponentSuspicious) && (
                  <div className="mt-4 rounded-2xl bg-[#0b1320] border border-white/10 p-3 text-[11px] opacity-85">
                    <div>
                      {t('pvp_flags', { defaultValue: 'Flags' })}:{' '}
                      <span className="font-mono">
                        {formatFlags(
                          isChallenge ? challengeVerdict?.flags : liveVerdicts.me?.flags
                        )}
                      </span>
                    </div>
                    {!isChallenge && opponentSuspicious ? (
                      <div className="mt-1">
                        {t('pvp_opponent_flags', { defaultValue: 'Opponent flags' })}:{' '}
                        <span className="font-mono">{formatFlags(liveVerdicts.opponent?.flags)}</span>
                      </div>
                    ) : null}
                  </div>
                )}
              </>
            )}

            <div className="mt-4">
              <button
                className="w-full rounded-2xl bg-[#00f0ff] text-black font-bold py-3 disabled:opacity-60"
                onClick={resetToLobby}
                disabled={loading}
              >
                {t('pvp_back_to_lobby', { defaultValue: 'Lobbiyə qayıt' })}
              </button>
            </div>
          </div>
        </div>
      );
    }

    return (
      <>
        {renderLobbyHeader()}

        <div className="mt-4 space-y-3">
          <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
            <div className="font-bold">{t('pvp_live_duel', { defaultValue: 'Canlı duel' })}</div>
            <div className="mt-2 text-xs opacity-80">
              {t('pvp_live_hint', { defaultValue: 'Dəvət linki yarat və rəqibinə göndər.' })}
            </div>

            <div className="mt-3 space-y-2">
              <button
                className="rounded-2xl bg-[#00f0ff] text-black font-bold py-3 w-full disabled:opacity-60"
                onClick={onCreateInvite}
                disabled={!canUse || loading}
              >
                {t('pvp_create_invite', { defaultValue: 'Dəvət yarat' })}
              </button>

              {createdInvite?.invite_code && (
                <div className="rounded-2xl bg-[#0b1320] border border-[#00f0ff20] p-3 text-xs">
                  <div className="opacity-80">{t('pvp_link', { defaultValue: 'Link:' })}</div>
                  <div className="font-mono break-all">{inviteUrl}</div>

                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <button
                      className="rounded-2xl bg-white/10 border border-white/10 py-2"
                      onClick={() => copyText(inviteUrl)}
                    >
                      {t('pvp_copy', { defaultValue: 'Kopyala' })}
                    </button>
                    <button
                      className="rounded-2xl bg-white/10 border border-white/10 py-2"
                      onClick={() => shareInvite(createdInvite.invite_code)}
                    >
                      {t('pvp_share', { defaultValue: 'Paylaş' })}
                    </button>
                  </div>

                  <button
                    className="mt-2 w-full rounded-2xl bg-white/10 border border-white/10 py-2"
                    onClick={onCancelInvite}
                    disabled={loading}
                  >
                    {t('pvp_cancel_invite', { defaultValue: 'Dəvəti ləğv et' })}
                  </button>

                  <div className="mt-2 text-[11px] opacity-70">
                    {t('pvp_waiting_opponent', { defaultValue: 'Rəqib gözlənilir…' })}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
            <div className="font-bold">{t('pvp_challenge_title', { defaultValue: 'Challenge' })}</div>
            <div className="mt-2 text-xs opacity-80">
              {t('pvp_challenge_hint', { defaultValue: 'Rəqibin best_result nəticəsinə qarşı oyna. Qələbə +1 victory verir.' })}
            </div>

            <div className="mt-2 text-xs opacity-85">
              {t('pvp_challenge_attempts', {
                left: challengeLeft == null ? '—' : challengeLeft,
                max: challengeDailyLimit,
                defaultValue: 'Cəhdlər: {{left}}/{{max}}',
              })}
            </div>

            <button
              className="mt-3 rounded-2xl bg-[#00f0ff] text-black font-bold py-3 w-full disabled:opacity-60"
              onClick={onChallengeStart}
              disabled={!canUse || loading || challengeLeft === 0}
            >
              {t('pvp_start_challenge', { defaultValue: 'Challenge başlat' })}
            </button>

            {challengeOpponent && (
              <div className="mt-3 rounded-2xl bg-[#0b1320] border border-[#00f0ff20] p-3 text-xs">
                <div className="opacity-80">{t('pvp_opponent_label', { defaultValue: 'Rəqib' })}:</div>
                <div className="mt-1 font-semibold">
                  {formatUserLabel(challengeOpponent, challengeOpponent?.user_id ?? null)}
                </div>
                <div className="mt-1 opacity-80">
                  {t('pvp_best_label', { defaultValue: 'best' })}:{' '}
                  <span className="font-mono">{intOrZero(challengeOpponent.best_result)}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </>
    );
  };

  return <div className="min-h-screen bg-[#07111e] px-4 pt-4 pb-24 text-white">{renderContent()}</div>;
};

export default Pvp;
