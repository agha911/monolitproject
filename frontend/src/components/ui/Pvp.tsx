import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import WebApp from '@twa-dev/sdk';
import API_BASE_URL from '../config';

function getTelegramId(): number | null {
  const id = WebApp.initDataUnsafe?.user?.id;
  return typeof id === 'number' ? id : null;
}

async function apiRequest<T>(path: string, opts?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(opts?.headers || {}),
    },
  });

  if (!res.ok) {
    let detail: any = null;
    try {
      detail = await res.json();
    } catch {
      /* ignore */
    }
    const msg = detail?.detail?.message || detail?.detail?.code || detail?.message || `HTTP ${res.status}`;
    throw new Error(msg);
  }

  return (await res.json()) as T;
}

type Screen = 'lobby' | 'duel' | 'result';
type DuelMode = 'live' | 'challenge';
type DuelPhase = 'prep' | 'active';

const PREP_SECONDS = 3;

function intOrZero(v: any): number {
  const n = Number(v);
  return Number.isFinite(n) ? Math.floor(n) : 0;
}

function pickVictories(me: any): number {
  return intOrZero(me?.victories ?? me?.pvp_victories);
}

function pickBest(me: any): number {
  return intOrZero(me?.best_result ?? me?.pvp_best_result);
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

  const [leaderboard, setLeaderboard] = useState<any[]>([]);

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

  const refreshLeaderboard = async () => {
    try {
      const res = await apiRequest<any>('/api/pvp/leaderboard');
      const items = Array.isArray(res?.items) ? res.items : [];
      setLeaderboard(items);
    } catch {
      // ignore
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
    refreshLeaderboard();
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

  const startActiveTimer = () => {
    stopDuelTimer();

    const startedAt = Date.now();
    duelTimerRef.current = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      const left = Math.max(0, matchDurationSec - elapsed);
      setDuelSecondsLeft(left);

      if (left <= 0) {
        stopDuelTimer();
        setScreen('result');
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

  /**
   * IMPORTANT: hard restart duel every time it is called:
   * - stops timers
   * - resets phase to prep
   * - starts countdown
   */
  const startDuel = (mode: DuelMode) => {
    setError('');
    setFinishResponse(null);
    setChallengeFinishResp(null);

    stopPrepTimer();
    stopDuelTimer();
    stopLivePoll();

    setDuelMode(mode);
    setScreen('duel');
    setPhase('prep');
    setMyClicks(0);
    setPrepSecondsLeft(PREP_SECONDS);
    setDuelSecondsLeft(matchDurationSec);
    setLiveSubmitState('idle');

    startPrepCountdown();
  };

  const resetToLobby = () => {
    setError('');
    setFinishResponse(null);
    setChallengeFinishResp(null);

    stopPrepTimer();
    stopDuelTimer();
    stopInvitePoll();
    stopLivePoll();

    setScreen('lobby');
    setPhase('prep');
    setMyClicks(0);
    setLiveSubmitState('idle');
    setMatchInfo(null);
    setChallengeStartResp(null);
    setChallengeAttemptId(null);
    setChallengeOpponent(null);
  };

  const onTap = () => {
    if (screen !== 'duel') return;
    if (phase !== 'active') return;
    setMyClicks((v) => v + 1);
  };

  const createInvite = async () => {
    if (!telegramId) return;
    setError('');
    setLoading(true);
    try {
      const body = { telegram_id: telegramId, ttl_seconds: 600 };
      const res = await apiRequest<any>('/api/pvp/invite/create', { method: 'POST', body: JSON.stringify(body) });
      setCreatedInvite(res);
      setMatchInfo(null);

      stopInvitePoll();
      invitePollRef.current = window.setInterval(async () => {
        try {
          const st = await apiRequest<any>(`/api/pvp/invite/status?invite_code=${encodeURIComponent(res.invite_code)}`);
          if (st?.ok && st?.status === 'accepted' && st?.match_token) {
            stopInvitePoll();
            setMatchInfo(st);
            startDuel('live');
          }
          if (st?.ok === false) {
            // invite not found / expired
          }
        } catch {
          // ignore poll errors
        }
      }, 1200);
    } catch (e: any) {
      setError(e?.message || 'invite create failed');
    } finally {
      setLoading(false);
    }
  };

  const cancelInvite = async () => {
    if (!telegramId) return;
    if (!createdInvite?.invite_code) return;
    setError('');
    setLoading(true);
    try {
      const body = { telegram_id: telegramId, invite_code: createdInvite.invite_code };
      await apiRequest<any>('/api/pvp/invite/cancel', { method: 'POST', body: JSON.stringify(body) });
      stopInvitePoll();
      setCreatedInvite(null);
    } catch (e: any) {
      setError(e?.message || 'invite cancel failed');
    } finally {
      setLoading(false);
    }
  };

  const joinMatchmaking = async () => {
    if (!telegramId) return;
    setError('');
    setLoading(true);
    try {
      const body = { telegram_id: telegramId };
      const res = await apiRequest<any>('/api/pvp/matchmaking/join', { method: 'POST', body: JSON.stringify(body) });
      setMatchInfo(res);

      // poll status until matched
      stopInvitePoll();
      invitePollRef.current = window.setInterval(async () => {
        try {
          const st = await apiRequest<any>(`/api/pvp/matchmaking/status?telegram_id=${telegramId}`);
          if (st?.ok && st?.status === 'matched' && st?.match_token) {
            stopInvitePoll();
            setMatchInfo(st);
            startDuel('live');
          }
          if (st?.ok && (st?.status === 'left' || st?.status === 'expired')) {
            stopInvitePoll();
            setMatchInfo(st);
          }
        } catch {
          // ignore
        }
      }, 1200);
    } catch (e: any) {
      setError(e?.message || 'matchmaking join failed');
    } finally {
      setLoading(false);
    }
  };

  const leaveMatchmaking = async () => {
    if (!telegramId) return;
    setError('');
    setLoading(true);
    try {
      const body = { telegram_id: telegramId };
      const res = await apiRequest<any>('/api/pvp/matchmaking/leave', { method: 'POST', body: JSON.stringify(body) });
      stopInvitePoll();
      setMatchInfo(res);
    } catch (e: any) {
      setError(e?.message || 'matchmaking leave failed');
    } finally {
      setLoading(false);
    }
  };

  const submitLive = async () => {
    if (!telegramId) return;
    if (!matchInfo?.match_token) return;

    setError('');
    setLoading(true);

    try {
      const body = { telegram_id: telegramId, match_token: matchInfo.match_token, my_clicks: myClicks };
      const res = await apiRequest<any>('/api/pvp/live/submit', { method: 'POST', body: JSON.stringify(body) });

      setLiveSubmitState('waiting');

      // if immediate finish
      if (res?.status === 'finished' && res?.result) {
        setFinishResponse(res);
        setLiveSubmitState('finished');
        setScreen('result');
        await refreshMe();
        await refreshLeaderboard();
        return;
      }

      // poll status
      stopLivePoll();
      livePollRef.current = window.setInterval(async () => {
        try {
          const st = await apiRequest<any>(
            `/api/pvp/live/status?telegram_id=${telegramId}&match_token=${encodeURIComponent(matchInfo.match_token)}`
          );
          if (st?.ok && st?.status === 'finished' && st?.result) {
            stopLivePoll();
            setFinishResponse(st);
            setLiveSubmitState('finished');
            setScreen('result');
            await refreshMe();
            await refreshLeaderboard();
          }
          if (st?.ok && st?.status === 'expired') {
            stopLivePoll();
            setFinishResponse(st);
            setLiveSubmitState('finished');
            setScreen('result');
            await refreshMe();
            await refreshLeaderboard();
          }
        } catch {
          // ignore
        }
      }, 1200);
    } catch (e: any) {
      setError(e?.message || 'submit failed');
    } finally {
      setLoading(false);
    }
  };

  const startChallenge = async () => {
    if (!telegramId) return;
    setError('');
    setLoading(true);

    try {
      const res = await apiRequest<any>(`/api/pvp/challenge/pick?telegram_id=${telegramId}`);
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

  const finishChallenge = async () => {
    if (!telegramId) return;
    if (!challengeAttemptId) return;

    setError('');
    setLoading(true);

    try {
      const body = { telegram_id: telegramId, attempt_id: challengeAttemptId, my_clicks: myClicks };
      const res = await apiRequest<any>('/api/pvp/challenge/finish', { method: 'POST', body: JSON.stringify(body) });
      setChallengeFinishResp(res);
      setScreen('result');
      await refreshMe();
      await refreshLeaderboard();
    } catch (e: any) {
      setError(e?.message || 'challenge finish failed');
    } finally {
      setLoading(false);
    }
  };

  const isChallenge = duelMode === 'challenge';
  const victories = pickVictories(meInfo);
  const best = pickBest(meInfo);

  return (
    <div className="min-h-screen bg-[#07111e] px-4 pt-4 pb-24 text-white">
      <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4 shadow-[0_0_12px_#00f0ff20]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-bold">⚔️ PvP</div>
            <div className="text-xs opacity-80">{t('pvp_subtitle', { defaultValue: 'Live duel & Challenge' })}</div>
          </div>
          <div className="text-right text-xs opacity-80">
            <div>stake: {stakeDefault}</div>
            <div>duration: {matchDurationSec}s</div>
          </div>
        </div>

        {!canUse && <div className="mt-3 text-xs text-[#ffadad]">Telegram initData is missing</div>}

        {error && <div className="mt-3 text-xs text-[#ffadad] whitespace-pre-wrap">{error}</div>}

        {meInfo && (
          <div className="mt-3 text-xs opacity-80">
            <div>
              you: #{meInfo.user_id} @{meInfo.username || '—'}
            </div>
            <div>victories: {victories} | best: {best}</div>
          </div>
        )}
      </div>

      <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4 shadow-[0_0_12px_#00f0ff20]">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">🏆 {t('pvp_weekly_leaderboard', { defaultValue: 'Weekly leaderboard' })}</div>
          <button
            className="text-xs opacity-80 underline underline-offset-2"
            onClick={refreshLeaderboard}
            disabled={loading}
          >
            {t('refresh', { defaultValue: 'Refresh' })}
          </button>
        </div>

        {leaderboard.length === 0 ? (
          <div className="mt-3 text-xs opacity-70">{t('pvp_no_leaderboard', { defaultValue: 'No data yet.' })}</div>
        ) : (
          <div className="mt-3 overflow-hidden rounded-xl border border-white/10">
            <table className="w-full text-left text-xs">
              <thead className="bg-white/5">
                <tr>
                  <th className="px-3 py-2 w-10">#</th>
                  <th className="px-3 py-2">{t('player', { defaultValue: 'Player' })}</th>
                  <th className="px-3 py-2 w-24 text-right">{t('victories', { defaultValue: 'Victories' })}</th>
                  <th className="px-3 py-2 w-24 text-right">{t('best', { defaultValue: 'Best' })}</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((u: any, idx: number) => {
                  const isMe = meInfo?.user_id && u?.user_id === meInfo.user_id;
                  const name = u?.username
                    ? `@${u.username}`
                    : u?.first_name || u?.last_name
                    ? `${u.first_name || ''} ${u.last_name || ''}`.trim()
                    : `#${u?.user_id ?? '—'}`;

                  return (
                    <tr key={u?.user_id ?? idx} className={isMe ? 'bg-white/10' : 'bg-transparent'}>
                      <td className="px-3 py-2">{idx + 1}</td>
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

      {/* LOBBY */}
      {screen === 'lobby' && (
        <div className="mt-4 space-y-3">
          <div className="rounded-2xl bg-[#0e1a2b] border border-white/10 p-4">
            <div className="text-sm font-semibold">{t('pvp_live', { defaultValue: 'Live PvP' })}</div>
            <div className="mt-2 flex gap-2">
              <button
                className="flex-1 rounded-xl bg-white/10 hover:bg-white/15 border border-white/10 px-4 py-3 text-sm"
                onClick={createInvite}
                disabled={!canUse || loading}
              >
                {t('pvp_create_invite', { defaultValue: 'Create invite link' })}
              </button>
              <button
                className="flex-1 rounded-xl bg-white/10 hover:bg-white/15 border border-white/10 px-4 py-3 text-sm"
                onClick={joinMatchmaking}
                disabled={!canUse || loading}
              >
                {t('pvp_matchmaking', { defaultValue: 'Random matchmaking' })}
              </button>
            </div>

            {createdInvite?.invite_code && (
              <div className="mt-3 rounded-xl border border-white/10 bg-white/5 p-3 text-xs">
                <div className="opacity-80">{t('pvp_invite_created', { defaultValue: 'Invite created' })}</div>
                <div className="mt-1">
                  code: <span className="font-mono">{createdInvite.invite_code}</span>
                </div>
                <div className="mt-1">
                  start_param: <span className="font-mono">{createdInvite.start_param}</span>
                </div>
                <div className="mt-2 flex gap-2">
                  <button
                    className="rounded-lg bg-white/10 hover:bg-white/15 border border-white/10 px-3 py-2"
                    onClick={() => {
                      try {
                        const link = `https://t.me/${WebApp.initDataUnsafe?.user?.username || ''}?start=${createdInvite.start_param}`;
                        WebApp.openTelegramLink(link);
                      } catch {}
                    }}
                    disabled={loading}
                  >
                    {t('share', { defaultValue: 'Share' })}
                  </button>
                  <button
                    className="rounded-lg bg-white/10 hover:bg-white/15 border border-white/10 px-3 py-2"
                    onClick={cancelInvite}
                    disabled={loading}
                  >
                    {t('cancel', { defaultValue: 'Cancel' })}
                  </button>
                </div>
              </div>
            )}

            {matchInfo?.status === 'waiting' && (
              <div className="mt-3 text-xs opacity-80">
                {t('pvp_waiting_opponent', { defaultValue: 'Waiting for opponent…' })}
              </div>
            )}

            {matchInfo?.status === 'left' && (
              <div className="mt-3 text-xs opacity-80">
                {t('pvp_left_queue', { defaultValue: 'You left matchmaking queue.' })}
              </div>
            )}

            {matchInfo?.status === 'expired' && (
              <div className="mt-3 text-xs opacity-80">
                {t('pvp_queue_expired', { defaultValue: 'Queue expired.' })}
              </div>
            )}

            {matchInfo?.status === 'waiting' && (
              <div className="mt-2">
                <button
                  className="w-full rounded-xl bg-white/10 hover:bg-white/15 border border-white/10 px-4 py-3 text-sm"
                  onClick={leaveMatchmaking}
                  disabled={!canUse || loading}
                >
                  {t('pvp_leave_queue', { defaultValue: 'Leave queue' })}
                </button>
              </div>
            )}
          </div>

          <div className="rounded-2xl bg-[#0e1a2b] border border-white/10 p-4">
            <div className="text-sm font-semibold">{t('pvp_challenge', { defaultValue: 'Challenge (no stake)' })}</div>
            <div className="mt-2">
              <button
                className="w-full rounded-xl bg-white/10 hover:bg-white/15 border border-white/10 px-4 py-3 text-sm"
                onClick={startChallenge}
                disabled={!canUse || loading}
              >
                {t('pvp_start_challenge', { defaultValue: 'Start challenge' })}
              </button>
            </div>

            {challengeStartResp?.ok && challengeOpponent && (
              <div className="mt-3 rounded-xl border border-white/10 bg-white/5 p-3 text-xs">
                <div className="opacity-80">{t('pvp_opponent', { defaultValue: 'Opponent' })}</div>
                <div className="mt-1">
                  #{challengeOpponent.user_id} @{challengeOpponent.username || '—'}
                </div>
                <div className="mt-1">
                  best: <span className="font-mono">{intOrZero(challengeOpponent.best_result)}</span>
                </div>
              </div>
            )}
          </div>

          <div className="rounded-2xl bg-[#0e1a2b] border border-white/10 p-4">
            <div className="text-xs opacity-80">
              {t('pvp_tip', {
                defaultValue:
                  'Tip: Live win = +2 victories, Challenge win = +1. Weekly victories reset automatically by season.',
              })}
            </div>
          </div>
        </div>
      )}

      {/* DUEL */}
      {screen === 'duel' && (
        <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4 shadow-[0_0_12px_#00f0ff20]">
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold">
              {isChallenge ? '🧪 Challenge' : '⚔️ Live'}
              <span className="ml-2 text-xs opacity-70">{phase === 'prep' ? 'prep' : 'active'}</span>
            </div>
            <div className="text-xs opacity-80">
              {phase === 'prep' ? (
                <span>
                  {t('starts_in', { defaultValue: 'starts in' })}: {prepSecondsLeft}s
                </span>
              ) : (
                <span>
                  {t('time_left', { defaultValue: 'time left' })}: {duelSecondsLeft}s
                </span>
              )}
            </div>
          </div>

          <div className="mt-4 flex flex-col items-center justify-center">
            <div
              onPointerDown={onTap}
              className="select-none rounded-2xl bg-white/10 border border-white/15 w-full py-10 text-center active:scale-[0.99] transition"
              style={{ touchAction: 'manipulation' }}
            >
              <div className="text-4xl font-bold">{myClicks}</div>
              <div className="mt-2 text-xs opacity-70">{t('tap_to_click', { defaultValue: 'Tap to click' })}</div>
            </div>

            {phase === 'prep' && (
              <div className="mt-4 flex items-center justify-center">
                <div className="rounded-2xl bg-black/60 border border-white/20 px-6 py-4 text-center">
                  <div className="text-sm opacity-90">Get ready</div>
                  <div className="text-3xl font-bold">{prepSecondsLeft}</div>
                </div>
              </div>
            )}

            <div className="mt-4 w-full flex gap-2">
              {!isChallenge ? (
                <button
                  className="flex-1 rounded-xl bg-white/10 hover:bg-white/15 border border-white/10 px-4 py-3 text-sm"
                  onClick={submitLive}
                  disabled={loading || liveSubmitState !== 'idle'}
                >
                  {liveSubmitState === 'idle'
                    ? t('submit', { defaultValue: 'Submit' })
                    : t('waiting', { defaultValue: 'Waiting…' })}
                </button>
              ) : (
                <button
                  className="flex-1 rounded-xl bg-white/10 hover:bg-white/15 border border-white/10 px-4 py-3 text-sm"
                  onClick={finishChallenge}
                  disabled={loading}
                >
                  {t('finish', { defaultValue: 'Finish' })}
                </button>
              )}

              <button
                className="rounded-xl bg-white/10 hover:bg-white/15 border border-white/10 px-4 py-3 text-sm"
                onClick={resetToLobby}
                disabled={loading}
              >
                {t('back', { defaultValue: 'Back' })}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* RESULT */}
      {screen === 'result' && (
        <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-white/10 p-4">
          <div className="text-sm font-semibold">{t('result', { defaultValue: 'Result' })}</div>

          {!isChallenge ? (
            <div className="mt-2 text-xs opacity-80 whitespace-pre-wrap">
              {finishResponse ? JSON.stringify(finishResponse, null, 2) : t('no_data', { defaultValue: 'No data' })}
            </div>
          ) : (
            <div className="mt-2 text-xs opacity-80 whitespace-pre-wrap">
              {challengeFinishResp
                ? JSON.stringify(challengeFinishResp, null, 2)
                : t('no_data', { defaultValue: 'No data' })}
            </div>
          )}

          <div className="mt-4 flex gap-2">
            <button
              className="flex-1 rounded-xl bg-white/10 hover:bg-white/15 border border-white/10 px-4 py-3 text-sm"
              onClick={() => {
                resetToLobby();
                refreshMe();
                refreshLeaderboard();
              }}
              disabled={loading}
            >
              {t('to_lobby', { defaultValue: 'Back to lobby' })}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default Pvp;
