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
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return data as T;
}

type Screen = 'lobby' | 'duel' | 'result';
type DuelMode = 'live' | 'challenge';
type DuelPhase = 'prep' | 'active';

const BOT_USERNAME = 'monolit_42_bot';

function buildInviteLink(code: string) {
  return `https://t.me/${BOT_USERNAME}?startapp=pvp_${code}`;
}

function buildShareLink(url: string, text: string) {
  return `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;
}

function pickVictories(me: any): number {
  const v = me?.pvp_victories ?? me?.victories ?? me?.pvp_weekly_victories ?? me?.weekly_victories ?? 0;
  return Number.isFinite(Number(v)) ? Number(v) : 0;
}

function pickBest(me: any): number {
  const b = me?.pvp_best_result ?? me?.best_result ?? me?.best ?? me?.pvp_best ?? 0;
  return Number.isFinite(Number(b)) ? Number(b) : 0;
}

function intOrZero(v: any): number {
  const n = Number(v);
  return Number.isFinite(n) ? Math.floor(n) : 0;
}

const PREP_SECONDS = 5;

// glow tuning
const GLOW_WINDOW_MS = 700; // look-back window for click speed
const GLOW_MAX_CPS = 12; // 12 clicks per second = max glow
const GLOW_DECAY_PER_TICK = 0.05; // decay speed
const GLOW_TICK_MS = 45;

const Pvp: React.FC = () => {
  const { t } = useTranslation();

  const telegramId = useMemo(() => getTelegramId(), []);
  const canUse = !!telegramId && !!WebApp.initData;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  const [config, setConfig] = useState<any>(null);

  const [meUserId, setMeUserId] = useState<number | null>(null);
  const [meInfo, setMeInfo] = useState<any>(null);

  // Weekly season leaderboard
  const [weeklySeason, setWeeklySeason] = useState<any>(null);
  const [weeklyItems, setWeeklyItems] = useState<any[]>([]);
  const [weeklySource, setWeeklySource] = useState<string>('');
  const [weeklyLoading, setWeeklyLoading] = useState<boolean>(false);

  const [createdInvite, setCreatedInvite] = useState<any>(null);
  const invitePollRef = useRef<number | null>(null);

  const [matchInfo, setMatchInfo] = useState<any>(null);

  const [screen, setScreen] = useState<Screen>('lobby');
  const [duelMode, setDuelMode] = useState<DuelMode>('live');

  // countdown
  const [phase, setPhase] = useState<DuelPhase>('prep');
  const [prepSecondsLeft, setPrepSecondsLeft] = useState<number>(0);

  const [duelSecondsLeft, setDuelSecondsLeft] = useState<number>(0);
  const duelTimerRef = useRef<number | null>(null);
  const prepTimerRef = useRef<number | null>(null);

  const [myClicks, setMyClicks] = useState<number>(0);

  const [liveSubmitState, setLiveSubmitState] = useState<'idle' | 'waiting' | 'finished'>('idle');
  const livePollRef = useRef<number | null>(null);
  const [finishResponse, setFinishResponse] = useState<any>(null);

  const [challengeStartResp, setChallengeStartResp] = useState<any>(null);
  const [challengeAttemptId, setChallengeAttemptId] = useState<number | null>(null);
  const [challengeOpponent, setChallengeOpponent] = useState<any>(null);
  const [challengeFinishResp, setChallengeFinishResp] = useState<any>(null);

  const matchDurationSec = config?.match_duration_sec ?? 30;
  const stakeDefault = config?.stake ?? config?.stake_default ?? 50000;

  // -----------------------------
  // AUTO SUBMIT / AUTO FINISH
  // -----------------------------
  const autoEndTriggeredRef = useRef(false);
  const duelModeRef = useRef<DuelMode>('live');
  const liveSubmitStateRef = useRef<'idle' | 'waiting' | 'finished'>('idle');
  const challengeAttemptIdRef = useRef<number | null>(null);
  const myClicksRef = useRef<number>(0);

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

  const refreshMe = async () => {
    if (!telegramId) return;
    try {
      const me = await apiRequest<any>(`/api/pvp/me?telegram_id=${telegramId}`);
      if (me?.user_id) setMeUserId(me.user_id);
      setMeInfo(me);
    } catch {}
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
        setWeeklySource(lb?.source || '');
        return;
      } catch {}

      const legacy = await apiRequest<any>('/api/pvp/leaderboard');
      setWeeklySeason(season);
      setWeeklyItems(Array.isArray(legacy?.items) ? legacy.items : []);
      setWeeklySource('legacy');
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

  const pollLiveStatus = (matchToken: string) => {
    stopLivePoll();
    livePollRef.current = window.setInterval(async () => {
      if (!telegramId) return;
      try {
        const st = await apiRequest<any>(
          `/api/pvp/live/status?telegram_id=${telegramId}&match_token=${encodeURIComponent(matchToken)}`
        );

        if (st?.status === 'finished' && (st?.result || st?.match_id)) {
          setLiveSubmitState('finished');
          setFinishResponse(st?.result || st);
          stopLivePoll();
          await refreshMe();
          await refreshWeekly();
        }

        if (st?.status === 'expired') {
          setError('Session expired');
          stopLivePoll();
        }
      } catch {}
    }, 900);
  };

  const onLiveSubmit = async () => {
    if (!telegramId) return;
    const token = matchInfo?.match_token;
    if (!token) {
      setError('match_token missing');
      return;
    }

    // avoid double submit
    if (liveSubmitStateRef.current !== 'idle') return;

    setError('');
    setLoading(true);
    try {
      const res = await apiRequest<any>('/api/pvp/live/submit', {
        method: 'POST',
        body: JSON.stringify({
          telegram_id: telegramId,
          match_token: token,
          my_clicks: myClicksRef.current,
        }),
      });

      if (res?.status === 'finished') {
        setLiveSubmitState('finished');
        setFinishResponse(res);
        await refreshMe();
        await refreshWeekly();
      } else {
        setLiveSubmitState('waiting');
        pollLiveStatus(token);
      }
    } catch (e: any) {
      setError(e?.message || 'submit failed');
    } finally {
      setLoading(false);
    }
  };

  const onChallengeFinish = async () => {
    if (!telegramId) return;
    const attemptId = challengeAttemptIdRef.current;
    if (!attemptId) {
      setError('attempt_id missing');
      return;
    }

    setError('');
    setLoading(true);
    try {
      const res = await apiRequest<any>('/api/pvp/challenge/finish', {
        method: 'POST',
        body: JSON.stringify({
          telegram_id: telegramId,
          attempt_id: attemptId,
          my_clicks: myClicksRef.current,
        }),
      });
      setChallengeFinishResp(res);
      await refreshMe();
      await refreshWeekly();
    } catch (e: any) {
      setError(e?.message || 'challenge finish failed');
    } finally {
      setLoading(false);
    }
  };

  const triggerAutoEndIfNeeded = () => {
    if (autoEndTriggeredRef.current) return;
    autoEndTriggeredRef.current = true;

    // Always show result screen when time ends
    setScreen('result');

    // Fire-and-forget (user still has manual button as fallback)
    if (duelModeRef.current === 'challenge') {
      void onChallengeFinish();
      return;
    }

    void onLiveSubmit();
  };

  const startActiveTimer = () => {
    stopDuelTimer();

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

    setMyClicks(0);
    setLiveSubmitState('idle');
    stopLivePoll();

    // reset auto-end guard
    autoEndTriggeredRef.current = false;

    // HARD RESET TIMERS + PHASE
    stopPrepTimer();
    stopDuelTimer();
    setPhase('prep');
    setPrepSecondsLeft(PREP_SECONDS);

    setDuelMode(mode);
    setDuelSecondsLeft(matchDurationSec);
    setScreen('duel');

    startPrepCountdown();
  };

  // ---- AUTO-ACCEPT (receiver) — when opened by link (start_param = "pvp_<code>") ----
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

        if (data?.match_token) startDuel('live');
      } catch (e: any) {
        setError(e?.message || 'invite accept failed');
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [telegramId]);

  // -----------------------------
  // CLICK GLOW (speed -> brightness)
  // -----------------------------
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

    setGlow((prev) => Math.max(prev, intensity));
  };

  useEffect(() => {
    // decay loop
    if (glowTickRef.current) window.clearInterval(glowTickRef.current);
    glowTickRef.current = window.setInterval(() => {
      setGlow((prev) => {
        const next = Math.max(0, prev - GLOW_DECAY_PER_TICK);
        return next;
      });
    }, GLOW_TICK_MS);

    return () => {
      if (glowTickRef.current) {
        window.clearInterval(glowTickRef.current);
        glowTickRef.current = null;
      }
    };
  }, []);

  // ---- click handling (multitouch limited to 2) ----
  const addClicks = (delta: number) => {
    if (screen !== 'duel') return;
    if (phase !== 'active') return;
    if (duelSecondsLeft <= 0) return;

    const d = Math.max(0, delta);
    setMyClicks((prev) => prev + d);

    recentClicksRef.current.push({ ts: Date.now(), delta: d });
    computeGlow();
  };

  const onTouchStart = (e: React.TouchEvent) => {
    const delta = Math.min(e.changedTouches?.length || 1, 2);
    addClicks(delta);
  };

  const onMouseDown = () => addClicks(1);

  // Poll invite status for sender and auto-start duel when accepted
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
          };
          setMatchInfo(mi);
          stopInvitePoll();
          startDuel('live');
        }

        if (st?.status === 'expired' || st?.status === 'cancelled') stopInvitePoll();
      } catch {}
    }, 800);
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
      setChallengeStartResp(res);
      setChallengeAttemptId(res?.attempt_id ?? null);
      setChallengeOpponent(res?.opponent ?? null);
      startDuel('challenge');
    } catch (e: any) {
      setError(e?.message || 'challenge start failed');
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
      setError(e?.message || 'invite create failed');
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
      setError(e?.message || 'invite cancel failed');
    } finally {
      setLoading(false);
    }
  };

  const copyText = async (txt: string) => {
    try {
      await navigator.clipboard.writeText(txt);
      WebApp.showToast?.(t('copied', { defaultValue: 'Copied' }));
    } catch {}
  };

  const shareInvite = (code: string) => {
    const url = buildInviteLink(code);
    const text = t('pvp_invite_share_text', { defaultValue: '⚔️ Join my duel in Gappick! Open this link:' });
    const tgShare = buildShareLink(url, text);

    try {
      (WebApp as any).openTelegramLink?.(tgShare);
    } catch {
      window.open(tgShare, '_blank');
    }
  };

  const isChallenge = duelMode === 'challenge';
  const victories = pickVictories(meInfo);
  const best = pickBest(meInfo);

  const opponentUserId = computeOpponentUserId();
  const inviteUrl = createdInvite?.invite_code ? buildInviteLink(createdInvite.invite_code) : '';

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

  // -----------------------------
  // RENDER: isolate lobby vs duel/result
  // -----------------------------
  const renderLobbyHeader = () => (
    <>
      <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4 shadow-[0_0_12px_#00f0ff20]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-bold">⚔️ PvP</div>
            <div className="text-xs opacity-80">{t('pvp_subtitle', { defaultValue: 'Live duel & Challenge' })}</div>
          </div>
          <div className="text-right text-xs opacity-80">
            <div>
              {t('pvp_stake', { defaultValue: 'stake:' })} {stakeDefault}
            </div>
            <div>
              {t('pvp_duration', { defaultValue: 'müddət:' })} {matchDurationSec}s
            </div>
          </div>
        </div>

        {!canUse && (
          <div className="mt-3 text-xs text-[#ffadad]">
            {t('pvp_tg_init_missing', { defaultValue: 'Telegram initData tapılmadı' })}
          </div>
        )}

        {error && <div className="mt-3 text-xs text-[#ffadad] whitespace-pre-wrap">{error}</div>}

        {meInfo && (
          <div className="mt-3 text-xs opacity-80">
            <div>
              {t('pvp_you', {
                id: meInfo.user_id,
                username: meInfo.username || '—',
                defaultValue: 'you: #{{id}} @{{username}}',
              })}
            </div>
            <div>{t('pvp_stats', { v: victories, b: best, defaultValue: 'victories: {{v}} | best: {{b}}' })}</div>
          </div>
        )}
      </div>

      {/* Weekly leaderboard */}
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

        {weeklySource ? (
          <div className="mt-2 text-[10px] opacity-50">
            {t('pvp_source', { src: weeklySource, defaultValue: 'mənbə: {{src}}' })}
          </div>
        ) : null}
      </div>
    </>
  );

  const renderDuelHeader = () => (
    <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4 shadow-[0_0_12px_#00f0ff20]">
      <div className="flex items-center justify-between">
        <button
          className="rounded-xl bg-white/10 border border-white/10 px-3 py-2 text-sm"
          onClick={resetToLobby}
        >
          ← {t('back', { defaultValue: 'Geri' })}
        </button>

        <div className="text-center">
          <div className="text-sm font-semibold">
            {isChallenge ? t('pvp_challenge_title', { defaultValue: 'Challenge' }) : t('pvp_duel', { defaultValue: 'Duel' })}
          </div>
          <div className="text-[11px] opacity-75">
            {phase === 'prep' ? t('pvp_get_ready', { defaultValue: 'Hazır ol' }) : t('pvp_go', { defaultValue: 'Başla!' })}
          </div>
        </div>

        <div className="text-right">
          <div className="text-[11px] opacity-75">{t('time', { defaultValue: 'time' })}</div>
          <div className="text-xl font-extrabold">{phase === 'prep' ? `${prepSecondsLeft}` : `${duelSecondsLeft}`}</div>
        </div>
      </div>

      {error && <div className="mt-3 text-xs text-[#ffadad] whitespace-pre-wrap">{error}</div>}
    </div>
  );

  const renderContent = () => {
    if (screen === 'duel') {
      return (
        <div className="mt-4">
          {renderDuelHeader()}

          {/* clicker-like status row */}
          <div className="mt-4 grid grid-cols-3 gap-3">
            <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff20] p-3 text-center">
              <div className="text-[11px] opacity-70">{t('pvp_your_clicks', { defaultValue: 'Klik' })}</div>
              <div className="text-2xl font-extrabold">{myClicks}</div>
            </div>
            <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff20] p-3 text-center">
              <div className="text-[11px] opacity-70">{t('pvp_opponent', { defaultValue: 'Rəqib' })}</div>
              <div className="text-2xl font-extrabold">{opponentUserId ?? '—'}</div>
            </div>
            <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff20] p-3 text-center">
              <div className="text-[11px] opacity-70">{t('pvp_power', { defaultValue: 'Glow' })}</div>
              <div className="text-2xl font-extrabold">{Math.round(glow * 100)}%</div>
            </div>
          </div>

          {/* Bubble click button */}
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
                  boxShadow: '0 0 14px rgba(0,240,255,0.12)',
                }}
              >
                {/* glow layer */}
                <div className="absolute inset-0 rounded-full" style={bubbleGlowStyle} />

                {/* soft glass highlight */}
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
                      {t('pvp_speed_hint', { defaultValue: 'Sürət artdıqca glow güclənir' })}
                    </div>
                  )}
                </div>
              </button>
            </div>
          </div>

          {/* bottom actions (optional manual fallback) */}
          <div className="mt-6 space-y-2">
            {!isChallenge ? (
              <button
                className="w-full rounded-2xl bg-[#00f0ff] text-black font-bold py-3 disabled:opacity-60"
                onClick={onLiveSubmit}
                disabled={loading || liveSubmitState !== 'idle'}
              >
                {liveSubmitState === 'idle' ? 'Submit (manual)' : 'Waiting...'}
              </button>
            ) : (
              <button
                className="w-full rounded-2xl bg-[#00f0ff] text-black font-bold py-3 disabled:opacity-60"
                onClick={onChallengeFinish}
                disabled={loading}
              >
                Finish (manual)
              </button>
            )}

            <button className="w-full rounded-2xl bg-white/10 border border-white/10 py-3" onClick={resetToLobby}>
              Back
            </button>
          </div>
        </div>
      );
    }

    if (screen === 'result') {
      return (
        <div className="mt-4">
          {renderDuelHeader()}

          <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff20] p-4">
            <div className="text-base font-bold">🏁 Result</div>
            <div className="mt-2 text-xs opacity-80">
              {t('pvp_result_hint', { defaultValue: 'Auto submit/finish triggered at 0s. Buttons below are fallback.' })}
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-2xl bg-[#0b1320] border border-[#00f0ff20] p-3">
                <div className="text-[11px] opacity-70">{t('pvp_your_clicks', { defaultValue: 'Klik' })}</div>
                <div className="text-2xl font-extrabold">{myClicks}</div>
              </div>
              <div className="rounded-2xl bg-[#0b1320] border border-[#00f0ff20] p-3">
                <div className="text-[11px] opacity-70">{t('pvp_opponent', { defaultValue: 'Rəqib' })}</div>
                <div className="text-2xl font-extrabold">{opponentUserId ?? '—'}</div>
              </div>
            </div>

            <div className="mt-4 space-y-2">
              {duelMode === 'challenge' ? (
                <>
                  <button
                    disabled={loading}
                    onClick={onChallengeFinish}
                    className="w-full rounded-2xl bg-[#00f0ff] text-black font-bold py-3 disabled:opacity-60"
                  >
                    {loading ? 'Loading...' : 'Finish (fallback)'}
                  </button>
                  {challengeFinishResp && (
                    <div className="mt-3 text-xs whitespace-pre-wrap opacity-90">
                      {JSON.stringify(challengeFinishResp, null, 2)}
                    </div>
                  )}
                </>
              ) : (
                <>
                  <button
                    disabled={loading || liveSubmitState === 'finished'}
                    onClick={onLiveSubmit}
                    className="w-full rounded-2xl bg-[#00f0ff] text-black font-bold py-3 disabled:opacity-60"
                  >
                    {loading
                      ? 'Loading...'
                      : liveSubmitState === 'waiting'
                      ? 'Waiting opponent...'
                      : liveSubmitState === 'finished'
                      ? 'Finished'
                      : 'Submit (fallback)'}
                  </button>

                  {finishResponse && (
                    <div className="mt-3 text-xs whitespace-pre-wrap opacity-90">{JSON.stringify(finishResponse, null, 2)}</div>
                  )}
                </>
              )}

              <button className="w-full rounded-2xl bg-white/10 border border-white/10 py-3" onClick={resetToLobby}>
                Back to lobby
              </button>
            </div>
          </div>
        </div>
      );
    }

    // lobby
    return (
      <>
        {renderLobbyHeader()}

        <div className="mt-4 space-y-3">
          <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
            <div className="font-bold">{t('pvp_live_duel', { defaultValue: 'Canlı duel' })}</div>
            <div className="mt-2 text-xs opacity-80">{t('pvp_live_hint', { defaultValue: 'Dəvət linki yarat və rəqibinə göndər.' })}</div>

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
                    <button className="rounded-2xl bg-white/10 border border-white/10 py-2" onClick={() => copyText(inviteUrl)}>
                      Copy
                    </button>
                    <button
                      className="rounded-2xl bg-white/10 border border-white/10 py-2"
                      onClick={() => shareInvite(createdInvite.invite_code)}
                    >
                      Share
                    </button>
                  </div>

                  <button
                    className="mt-2 w-full rounded-2xl bg-white/10 border border-white/10 py-2"
                    onClick={onCancelInvite}
                    disabled={loading}
                  >
                    {t('pvp_cancel_invite', { defaultValue: 'Dəvəti ləğv et' })}
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
            <div className="font-bold">{t('pvp_challenge_title', { defaultValue: 'Challenge' })}</div>
            <div className="mt-2 text-xs opacity-80">
              {t('pvp_challenge_hint', { defaultValue: 'Rəqibin best_result nəticəsinə qarşı oyna. Qələbə +1 victory verir.' })}
            </div>

            <button
              className="mt-3 rounded-2xl bg-[#00f0ff] text-black font-bold py-3 w-full disabled:opacity-60"
              onClick={onChallengeStart}
              disabled={!canUse || loading}
            >
              Start challenge
            </button>

            {challengeOpponent && (
              <div className="mt-3 rounded-2xl bg-[#0b1320] border border-[#00f0ff20] p-3 text-xs">
                <div className="opacity-80">Opponent:</div>
                <div className="mt-1">
                  #{challengeOpponent.user_id} @{challengeOpponent.username || '—'}
                </div>
                <div className="mt-1">
                  best: <span className="font-mono">{intOrZero(challengeOpponent.best_result)}</span>
                </div>
              </div>
            )}

            {challengeStartResp && (
              <div className="mt-3 text-xs opacity-70 whitespace-pre-wrap">{JSON.stringify(challengeStartResp, null, 2)}</div>
            )}
          </div>
        </div>
      </>
    );
  };

  return <div className="min-h-screen bg-[#07111e] px-4 pt-4 pb-24 text-white">{renderContent()}</div>;
};

export default Pvp;
