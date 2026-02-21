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

const Pvp: React.FC = () => {
  const { t } = useTranslation();

  const telegramId = useMemo(() => getTelegramId(), []);
  const canUse = !!telegramId && !!WebApp.initData;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  const [config, setConfig] = useState<any>(null);

  // me (to know internal user_id)
  const [meUserId, setMeUserId] = useState<number | null>(null);
  const [meInfo, setMeInfo] = useState<any>(null);

  // invite create / accept
  const [inviteCode, setInviteCode] = useState('');
  const [createdInvite, setCreatedInvite] = useState<any>(null);
  const [acceptedInvite, setAcceptedInvite] = useState<any>(null);

  // matchmaking
  const [queueStatus, setQueueStatus] = useState<'idle' | 'waiting' | 'matched'>('idle');
  const [matchInfo, setMatchInfo] = useState<any>(null);
  const pollTimerRef = useRef<number | null>(null);

  // screens / duel
  const [screen, setScreen] = useState<Screen>('lobby');
  const [duelMode, setDuelMode] = useState<DuelMode>('live');

  const [duelSecondsLeft, setDuelSecondsLeft] = useState<number>(0);
  const duelTimerRef = useRef<number | null>(null);

  const [myClicks, setMyClicks] = useState<number>(0);
  const [opponentClicksInput, setOpponentClicksInput] = useState<string>(''); // debug (live)
  const [finishResponse, setFinishResponse] = useState<any>(null);

  // ---- Challenge (iron mode) state ----
  const [challengeStartResp, setChallengeStartResp] = useState<any>(null);
  const [challengeAttemptId, setChallengeAttemptId] = useState<number | null>(null);
  const [challengeOpponent, setChallengeOpponent] = useState<any>(null);
  const [challengeFinishResp, setChallengeFinishResp] = useState<any>(null);

  const matchDurationSec = config?.match_duration_sec ?? 30;
  const stakeDefault = config?.stake ?? config?.stake_default ?? 50000;

  useEffect(() => {
    // best effort: load config
    (async () => {
      try {
        const cfg = await apiRequest<any>('/api/pvp/config');
        setConfig(cfg);
      } catch {
        // config may not exist - ok
      }
    })();

    return () => {
      if (pollTimerRef.current) window.clearInterval(pollTimerRef.current);
      if (duelTimerRef.current) window.clearInterval(duelTimerRef.current);
    };
  }, []);

  useEffect(() => {
    // load /api/pvp/me so we can compute opponent_user_id reliably
    (async () => {
      if (!telegramId) return;
      try {
        const me = await apiRequest<any>(`/api/pvp/me?telegram_id=${telegramId}`);
        if (me?.user_id) setMeUserId(me.user_id);
        setMeInfo(me);
      } catch {
        // ignore
      }
    })();
  }, [telegramId]);

  const clearPolling = () => {
    if (pollTimerRef.current) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  const startPolling = () => {
    clearPolling();
    pollTimerRef.current = window.setInterval(async () => {
      if (!telegramId) return;
      try {
        const data = await apiRequest<any>(`/api/pvp/matchmaking/poll?telegram_id=${telegramId}`, {
          method: 'POST',
        });

        if (data?.status === 'matched') {
          setQueueStatus('matched');
          setMatchInfo(data);
          clearPolling();
        } else if (data?.status === 'waiting') {
          setQueueStatus('waiting');
        } else {
          setQueueStatus('idle');
        }
      } catch (e: any) {
        setError(e?.message || 'poll failed');
        setQueueStatus('idle');
        clearPolling();
      }
    }, 1200);
  };

  const onCreateInvite = async () => {
    if (!telegramId) return;
    setError('');
    setLoading(true);
    try {
      const data = await apiRequest<any>('/api/pvp/invite/create', {
        method: 'POST',
        body: JSON.stringify({
          telegram_id: telegramId,
          ttl_seconds: 3600,
        }),
      });
      setCreatedInvite(data);
    } catch (e: any) {
      setError(e?.message || 'invite create failed');
    } finally {
      setLoading(false);
    }
  };

  const onAcceptInvite = async () => {
    if (!telegramId) return;
    const code = inviteCode.trim();
    if (!code) return;

    setError('');
    setLoading(true);
    try {
      const data = await apiRequest<any>('/api/pvp/invite/accept', {
        method: 'POST',
        body: JSON.stringify({
          telegram_id: telegramId,
          invite_code: code,
        }),
      });
      setAcceptedInvite(data);
      setMatchInfo(data);
      if (data?.match_token) setQueueStatus('matched');
    } catch (e: any) {
      setError(e?.message || 'invite accept failed');
    } finally {
      setLoading(false);
    }
  };

  const onJoinQueue = async () => {
    if (!telegramId) return;
    setError('');
    setLoading(true);
    try {
      await apiRequest<any>('/api/pvp/matchmaking/join', {
        method: 'POST',
        body: JSON.stringify({
          telegram_id: telegramId,
          ttl_seconds: 120,
        }),
      });
      setQueueStatus('waiting');
      startPolling();
    } catch (e: any) {
      setError(e?.message || 'join failed');
      setQueueStatus('idle');
    } finally {
      setLoading(false);
    }
  };

  const onLeaveQueue = async () => {
    if (!telegramId) return;
    setError('');
    setLoading(true);
    try {
      await apiRequest<any>('/api/pvp/matchmaking/leave', {
        method: 'POST',
        body: JSON.stringify({
          telegram_id: telegramId,
        }),
      });
      setQueueStatus('idle');
      clearPolling();
    } catch (e: any) {
      setError(e?.message || 'leave failed');
    } finally {
      setLoading(false);
    }
  };

  const copyText = async (txt: string) => {
    try {
      await navigator.clipboard.writeText(txt);
      WebApp.showToast?.(t('copied', { defaultValue: 'Copied' }));
    } catch {
      // no-op
    }
  };

  const computeOpponentUserId = (): number | null => {
    if (!meUserId || !matchInfo) return null;
    const p1 = matchInfo.player1_id;
    const p2 = matchInfo.player2_id;
    if (typeof p1 !== 'number' || typeof p2 !== 'number') return null;
    if (p1 === meUserId) return p2;
    if (p2 === meUserId) return p1;
    return null;
  };

  const stopDuelTimer = () => {
    if (duelTimerRef.current) {
      window.clearInterval(duelTimerRef.current);
      duelTimerRef.current = null;
    }
  };

  const startDuel = (mode: DuelMode) => {
    setError('');
    setFinishResponse(null);
    setChallengeFinishResp(null);
    setOpponentClicksInput('');
    setMyClicks(0);

    setDuelMode(mode);
    setDuelSecondsLeft(matchDurationSec);
    setScreen('duel');

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

  // clicks: simple & stable (touch + mouse). Multitouch “up to 2 fingers” — best effort.
  const addClicks = (delta: number) => {
    if (screen !== 'duel') return;
    if (duelSecondsLeft <= 0) return;
    setMyClicks((prev) => prev + Math.max(0, delta));
  };

  const onTouchStart = (e: React.TouchEvent) => {
    // count changed touches, cap at 2
    const delta = Math.min(e.changedTouches?.length || 1, 2);
    addClicks(delta);
  };

  const onMouseDown = () => addClicks(1);

  // -------------------------
  // LIVE finish (debug)
  // -------------------------
  const onFinishDebug = async () => {
    if (!telegramId) return;
    if (!matchInfo?.match_token) {
      setError('match_token missing');
      return;
    }
    const opponentUserId = computeOpponentUserId();
    if (!opponentUserId) {
      setError('opponent_user_id missing (need /api/pvp/me + player1_id/player2_id in matchInfo)');
      return;
    }

    const oppClicks = opponentClicksInput.trim() === '' ? 0 : Number(opponentClicksInput);
    if (Number.isNaN(oppClicks) || oppClicks < 0) {
      setError('opponent_clicks must be >= 0');
      return;
    }

    setError('');
    setLoading(true);
    try {
      const res = await apiRequest<any>('/api/pvp/live/finish', {
        method: 'POST',
        body: JSON.stringify({
          telegram_id: telegramId,
          match_token: matchInfo.match_token,
          opponent_user_id: opponentUserId,
          my_clicks: myClicks,
          opponent_clicks: oppClicks,
        }),
      });
      setFinishResponse(res);
    } catch (e: any) {
      setError(e?.message || 'finish failed');
    } finally {
      setLoading(false);
    }
  };

  // -------------------------
  // CHALLENGE (iron)
  // -------------------------
  const onChallengeStart = async () => {
    if (!telegramId) return;
    setError('');
    setLoading(true);
    try {
      const res = await apiRequest<any>('/api/pvp/challenge/start', {
        method: 'POST',
        body: JSON.stringify({ telegram_id: telegramId }),
      });
      // expected:
      // { ok, attempt_id, match_duration_sec, attempts_today, attempts_left, opponent:{...} }
      setChallengeStartResp(res);
      setChallengeAttemptId(res?.attempt_id ?? null);
      setChallengeOpponent(res?.opponent ?? null);

      // start duel in challenge mode
      startDuel('challenge');
    } catch (e: any) {
      setError(e?.message || 'challenge start failed');
    } finally {
      setLoading(false);
    }
  };

  const onChallengeFinish = async () => {
    if (!telegramId) return;
    if (!challengeAttemptId) {
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
          attempt_id: challengeAttemptId,
          my_clicks: myClicks,
        }),
      });
      setChallengeFinishResp(res);

      // refresh me info for UI
      try {
        const me = await apiRequest<any>(`/api/pvp/me?telegram_id=${telegramId}`);
        if (me?.user_id) setMeUserId(me.user_id);
        setMeInfo(me);
      } catch {
        // ignore
      }
    } catch (e: any) {
      setError(e?.message || 'challenge finish failed');
    } finally {
      setLoading(false);
    }
  };

  const resetToLobby = () => {
    stopDuelTimer();
    setScreen('lobby');
    setMyClicks(0);
    setOpponentClicksInput('');
    setFinishResponse(null);

    // challenge state reset
    setChallengeFinishResp(null);
    setChallengeAttemptId(null);
    setChallengeOpponent(null);
    // keep challengeStartResp so user can see attempts_left in lobby (optional)
    // leave queue state as-is; user may want to reuse matchInfo
  };

  const isChallenge = duelMode === 'challenge';

  return (
    <div className="px-4 pt-4 text-white">
      <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4 shadow-[0_0_12px_#00f0ff20]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-bold">⚔️ PvP</div>
            <div className="text-xs opacity-80">
              {t('pvp_subtitle', { defaultValue: 'Live duel & Challenge' })}
            </div>
          </div>
          <div className="text-right text-xs opacity-80">
            <div>stake: {stakeDefault}</div>
            <div>duration: {matchDurationSec}s</div>
          </div>
        </div>

        {!canUse && (
          <div className="mt-3 text-xs text-[#ffadad]">
            Telegram initData is missing (WebApp opened outside Telegram?)
          </div>
        )}

        {error && (
          <div className="mt-3 text-xs text-[#ffadad] whitespace-pre-wrap">
            {error}
          </div>
        )}
      </div>

      {/* DUEL SCREEN */}
      {screen === 'duel' && (
        <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
          <div className="flex items-start justify-between">
            <div>
              <div className="font-bold text-base">
                🔥 {isChallenge ? t('challenge', { defaultValue: 'Challenge' }) : t('pvp_duel', { defaultValue: 'Duel' })}
              </div>

              {!isChallenge && (
                <div className="text-xs opacity-80">
                  match_token: <span className="font-mono">{matchInfo?.match_token ?? '—'}</span>
                </div>
              )}

              {isChallenge && (
                <div className="text-xs opacity-80">
                  attempt_id: <span className="font-mono">{challengeAttemptId ?? '—'}</span>
                  {challengeOpponent?.user_id ? (
                    <div className="mt-1">
                      opponent_id: <span className="font-mono">{challengeOpponent.user_id}</span> | best:{' '}
                      <span className="font-mono">{challengeOpponent.best_result ?? 0}</span>
                    </div>
                  ) : null}
                </div>
              )}
            </div>

            <div className="text-right">
              <div className="text-xs opacity-80">{t('time_left', { defaultValue: 'Time left' })}</div>
              <div className="text-2xl font-extrabold">{duelSecondsLeft}s</div>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-[#0b1320] border border-[#00f0ff20] p-3">
              <div className="text-xs opacity-70">{t('your_clicks', { defaultValue: 'Your clicks' })}</div>
              <div className="text-2xl font-extrabold">{myClicks}</div>
            </div>

            {!isChallenge ? (
              <div className="rounded-xl bg-[#0b1320] border border-[#00f0ff20] p-3">
                <div className="text-xs opacity-70">{t('opponent', { defaultValue: 'Opponent' })}</div>
                <div className="text-sm opacity-90">
                  id: <span className="font-mono">{computeOpponentUserId() ?? '—'}</span>
                </div>
                <div className="text-xs opacity-60 mt-1">(for now calculated via /api/pvp/me)</div>
              </div>
            ) : (
              <div className="rounded-xl bg-[#0b1320] border border-[#00f0ff20] p-3">
                <div className="text-xs opacity-70">{t('opponent', { defaultValue: 'Opponent' })}</div>
                <div className="text-sm opacity-90">
                  id: <span className="font-mono">{challengeOpponent?.user_id ?? '—'}</span>
                </div>
                <div className="text-xs opacity-60 mt-1">
                  best: <span className="font-mono">{challengeOpponent?.best_result ?? 0}</span>
                </div>
              </div>
            )}
          </div>

          <div className="mt-4">
            <div
              onTouchStart={onTouchStart}
              onMouseDown={onMouseDown}
              className="select-none w-full h-40 rounded-2xl border border-[#00f0ff50] bg-[#0b1320] flex items-center justify-center active:scale-[0.99] shadow-[0_0_18px_#00f0ff20]"
            >
              <div className="text-center">
                <div className="text-2xl font-extrabold">{t('tap', { defaultValue: 'TAP' })}</div>
                <div className="text-xs opacity-70">{t('pvp_multitouch_hint', { defaultValue: 'multitouch up to 2 fingers' })}</div>
              </div>
            </div>
          </div>

          <button
            onClick={() => setScreen('result')}
            className="mt-3 w-full rounded-xl border border-[#00f0ff40] py-2 text-xs hover:bg-[#00f0ff10]"
          >
            {t('finish', { defaultValue: 'Finish' })}
          </button>
        </div>
      )}

      {/* RESULT SCREEN */}
      {screen === 'result' && (
        <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
          <div className="font-bold text-base">
            🧾 {t('result', { defaultValue: 'Result' })} {isChallenge ? '(Challenge)' : '(Live)'}
          </div>

          <div className="mt-2 text-sm">
            {t('your_clicks', { defaultValue: 'Your clicks' })}: <span className="font-mono">{myClicks}</span>
          </div>

          {/* Challenge result */}
          {isChallenge ? (
            <>
              <div className="mt-2 text-xs opacity-80">
                attempt_id: <span className="font-mono">{challengeAttemptId ?? '—'}</span> | opponent_best:{' '}
                <span className="font-mono">{challengeOpponent?.best_result ?? 0}</span>
              </div>

              {!challengeFinishResp ? (
                <button
                  disabled={!canUse || loading || !challengeAttemptId}
                  onClick={onChallengeFinish}
                  className="mt-3 w-full rounded-xl bg-[#00f0ff] text-black font-bold py-2 active:scale-95 disabled:opacity-50"
                >
                  {t('send_result', { defaultValue: 'Send result' })}
                </button>
              ) : (
                <div className="mt-3 rounded-xl bg-[#0b1320] border border-[#00f0ff20] p-3 text-sm">
                  <div>
                    is_win: <span className="font-mono">{String(challengeFinishResp.is_win)}</span>
                  </div>
                  <div>
                    victories_delta: <span className="font-mono">{challengeFinishResp.victories_delta ?? '—'}</span>
                  </div>
                  <div>
                    match_id: <span className="font-mono">{challengeFinishResp.match_id ?? '—'}</span>
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              {/* Live debug UI */}
              <div className="mt-3 rounded-xl bg-[#0b1320] border border-[#00f0ff20] p-3">
                <div className="text-xs opacity-80 mb-2">
                  Debug: set opponent_clicks manually then call /api/pvp/live/finish
                </div>

                <input
                  value={opponentClicksInput}
                  onChange={(e) => setOpponentClicksInput(e.target.value)}
                  placeholder="opponent_clicks (debug)"
                  className="w-full rounded-xl bg-[#0b1320] border border-[#00f0ff30] px-3 py-2 text-white outline-none"
                />

                <button
                  disabled={!canUse || loading}
                  onClick={onFinishDebug}
                  className="mt-2 w-full rounded-xl bg-[#7af9ff] text-black font-bold py-2 active:scale-95 disabled:opacity-50"
                >
                  {t('finish_debug', { defaultValue: 'Finish (debug)' })}
                </button>

                {finishResponse ? (
                  <div className="mt-3 text-xs whitespace-pre-wrap opacity-90">
                    {JSON.stringify(finishResponse, null, 2)}
                  </div>
                ) : null}
              </div>
            </>
          )}

          <button
            onClick={resetToLobby}
            className="mt-4 w-full rounded-xl border border-[#00f0ff40] py-2 text-xs hover:bg-[#00f0ff10]"
          >
            {t('back', { defaultValue: 'Back' })}
          </button>
        </div>
      )}

      {/* LOBBY */}
      {screen === 'lobby' && (
        <>
          {/* Invite */}
          <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
            <div className="font-bold mb-2">{t('pvp_invite', { defaultValue: 'Invite duel' })}</div>

            <button
              disabled={!canUse || loading}
              onClick={onCreateInvite}
              className="w-full rounded-xl bg-[#00f0ff] text-black font-bold py-2 active:scale-95 disabled:opacity-50"
            >
              {t('pvp_create_invite', { defaultValue: 'Create invite link' })}
            </button>

            {createdInvite?.invite_code && (
              <div className="mt-3 text-sm">
                <div className="opacity-80">invite_code:</div>
                <div className="flex items-center justify-between gap-2">
                  <div className="font-mono">{createdInvite.invite_code}</div>
                  <button
                    onClick={() => copyText(createdInvite.invite_code)}
                    className="text-xs px-3 py-1 rounded-lg border border-[#00f0ff40] hover:bg-[#00f0ff10]"
                  >
                    {t('copy', { defaultValue: 'Copy' })}
                  </button>
                </div>

                {createdInvite.start_param && (
                  <>
                    <div className="opacity-80 mt-2">start_param:</div>
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-mono text-xs break-all">{createdInvite.start_param}</div>
                      <button
                        onClick={() => copyText(createdInvite.start_param)}
                        className="text-xs px-3 py-1 rounded-lg border border-[#00f0ff40] hover:bg-[#00f0ff10]"
                      >
                        {t('copy', { defaultValue: 'Copy' })}
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            <div className="mt-4 border-t border-[#00f0ff20] pt-3">
              <div className="text-sm opacity-80 mb-2">{t('pvp_enter_code', { defaultValue: 'Enter invite code' })}</div>

              <input
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                placeholder="ABC123..."
                className="w-full rounded-xl bg-[#0b1320] border border-[#00f0ff30] px-3 py-2 text-white outline-none"
              />

              <button
                disabled={!canUse || loading || !inviteCode.trim()}
                onClick={onAcceptInvite}
                className="mt-2 w-full rounded-xl bg-[#7af9ff] text-black font-bold py-2 active:scale-95 disabled:opacity-50"
              >
                {t('pvp_accept_invite', { defaultValue: 'Accept invite' })}
              </button>

              {acceptedInvite?.match_token && (
                <div className="mt-3 text-xs opacity-80">
                  match_token: <span className="font-mono">{acceptedInvite.match_token}</span>
                  {acceptedInvite.expires_at ? (
                    <div>
                      expires_at: <span className="font-mono">{acceptedInvite.expires_at}</span>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          </div>

          {/* Matchmaking */}
          <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
            <div className="font-bold mb-2">{t('pvp_matchmaking', { defaultValue: 'Matchmaking' })}</div>

            {queueStatus !== 'waiting' && (
              <button
                disabled={!canUse || loading}
                onClick={onJoinQueue}
                className="w-full rounded-xl bg-[#00f0ff] text-black font-bold py-2 active:scale-95 disabled:opacity-50"
              >
                {t('pvp_find_opponent', { defaultValue: 'Find opponent' })}
              </button>
            )}

            {queueStatus === 'waiting' && (
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm opacity-80">{t('pvp_waiting', { defaultValue: 'Searching…' })}</div>
                <button
                  disabled={!canUse || loading}
                  onClick={onLeaveQueue}
                  className="text-xs px-3 py-2 rounded-xl border border-[#00f0ff40] hover:bg-[#00f0ff10] disabled:opacity-50"
                >
                  {t('cancel', { defaultValue: 'Cancel' })}
                </button>
              </div>
            )}

            {queueStatus === 'matched' && matchInfo?.match_token && (
              <div className="mt-3 text-sm">
                <div className="font-bold">✅ {t('pvp_matched', { defaultValue: 'Matched!' })}</div>

                <div className="text-xs opacity-80 mt-1">
                  match_token: <span className="font-mono">{matchInfo.match_token}</span>
                  {matchInfo.expires_at ? (
                    <div>
                      expires_at: <span className="font-mono">{matchInfo.expires_at}</span>
                    </div>
                  ) : null}
                  {matchInfo.match_duration_sec ? <div>duration: {matchInfo.match_duration_sec}s</div> : null}
                </div>

                <button
                  disabled={!canUse || loading}
                  onClick={() => startDuel('live')}
                  className="mt-3 w-full rounded-xl bg-[#00f0ff] text-black font-bold py-2 active:scale-95 disabled:opacity-50"
                >
                  {t('pvp_start_duel', { defaultValue: 'Start duel' })}
                </button>

                <div className="mt-2 text-xs opacity-60">
                  opponent_user_id: <span className="font-mono">{computeOpponentUserId() ?? '—'}</span>
                </div>
              </div>
            )}
          </div>

          {/* Challenge (iron) */}
          <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
            <div className="flex items-center justify-between">
              <div className="font-bold">{t('challenge', { defaultValue: 'Challenge' })}</div>
              <div className="text-xs opacity-80">
                {t('daily_limit', { defaultValue: 'Daily limit' })}: {challengeStartResp?.attempts_today ?? '—'}/5
              </div>
            </div>

            <div className="mt-1 text-xs opacity-70">
              {t('challenge_hint', {
                defaultValue: 'If you have no one to duel with — play offline. 5 tries per day.',
              })}
            </div>

            {challengeStartResp?.attempts_left !== undefined && (
              <div className="mt-2 text-xs opacity-80">
                attempts_left: <span className="font-mono">{challengeStartResp.attempts_left}</span>
              </div>
            )}

            <button
              disabled={!canUse || loading}
              onClick={onChallengeStart}
              className="mt-3 w-full rounded-xl bg-[#7af9ff] text-black font-bold py-2 active:scale-95 disabled:opacity-50"
            >
              {t('challenge_start', { defaultValue: 'Start challenge' })}
            </button>

            {challengeOpponent?.user_id ? (
              <div className="mt-3 text-xs opacity-80">
                opponent_id: <span className="font-mono">{challengeOpponent.user_id}</span> | opponent_best:{' '}
                <span className="font-mono">{challengeOpponent.best_result ?? 0}</span>
              </div>
            ) : null}
          </div>

          {/* Debug/info */}
          <div className="mt-4 text-xs opacity-60">
            telegram_id: {telegramId ?? '—'} | my_user_id: {meUserId ?? '—'} | victories:{' '}
            {meInfo?.victories ?? '—'} | best:{meInfo?.best_result ?? '—'}
          </div>
        </>
      )}
    </div>
  );
};

export default Pvp;
