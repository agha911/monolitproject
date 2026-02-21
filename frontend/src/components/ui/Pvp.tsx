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

const BOT_USERNAME =
  (import.meta as any)?.env?.VITE_TELEGRAM_BOT_USERNAME ||
  (window as any)?.__BOT_USERNAME__ ||
  'gappick_bot';

function buildInviteLink(code: string) {
  return `https://t.me/${BOT_USERNAME}?startapp=pvp_${code}`;
}

function buildShareLink(url: string, text: string) {
  return `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;
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

  const [inviteCode, setInviteCode] = useState('');
  const [createdInvite, setCreatedInvite] = useState<any>(null);
  const invitePollRef = useRef<number | null>(null);

  const [queueStatus, setQueueStatus] = useState<'idle' | 'waiting' | 'matched'>('idle');
  const [matchInfo, setMatchInfo] = useState<any>(null);
  const pollTimerRef = useRef<number | null>(null);

  const [screen, setScreen] = useState<Screen>('lobby');
  const [duelMode, setDuelMode] = useState<DuelMode>('live');

  const [duelSecondsLeft, setDuelSecondsLeft] = useState<number>(0);
  const duelTimerRef = useRef<number | null>(null);

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

  const stopQueuePoll = () => {
    if (pollTimerRef.current) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  const stopLivePoll = () => {
    if (livePollRef.current) {
      window.clearInterval(livePollRef.current);
      livePollRef.current = null;
    }
  };

  const stopDuelTimer = () => {
    if (duelTimerRef.current) {
      window.clearInterval(duelTimerRef.current);
      duelTimerRef.current = null;
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
      stopQueuePoll();
      stopDuelTimer();
      stopInvitePoll();
      stopLivePoll();
    };
  }, []);

  useEffect(() => {
    (async () => {
      if (!telegramId) return;
      try {
        const me = await apiRequest<any>(`/api/pvp/me?telegram_id=${telegramId}`);
        if (me?.user_id) setMeUserId(me.user_id);
        setMeInfo(me);
      } catch {}
    })();
  }, [telegramId]);

  useEffect(() => {
    // Auto-accept by deep link: start_param = pvp_<code>
    const sp = (WebApp.initDataUnsafe as any)?.start_param;
    if (!telegramId) return;
    if (!sp || typeof sp !== 'string') return;
    if (!sp.startsWith('pvp_')) return;

    const code = sp.replace('pvp_', '').trim();
    if (!code) return;

    setInviteCode(code);

    (async () => {
      setError('');
      setLoading(true);
      try {
        const data = await apiRequest<any>('/api/pvp/invite/accept', {
          method: 'POST',
          body: JSON.stringify({ telegram_id: telegramId, invite_code: code }),
        });
        setMatchInfo(data);
        setQueueStatus(data?.match_token ? 'matched' : 'idle');

        if (data?.match_token) startDuel('live');
      } catch (e: any) {
        setError(e?.message || 'invite accept failed');
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [telegramId]);

  const startQueuePolling = () => {
    stopQueuePoll();
    pollTimerRef.current = window.setInterval(async () => {
      if (!telegramId) return;
      try {
        const data = await apiRequest<any>(`/api/pvp/matchmaking/poll?telegram_id=${telegramId}`, { method: 'POST' });
        if (data?.status === 'matched') {
          setQueueStatus('matched');
          setMatchInfo(data);
          stopQueuePoll();
        } else if (data?.status === 'waiting') {
          setQueueStatus('waiting');
        } else {
          setQueueStatus('idle');
        }
      } catch (e: any) {
        setError(e?.message || 'poll failed');
        setQueueStatus('idle');
        stopQueuePoll();
      }
    }, 1200);
  };

  const startInvitePolling = (code: string) => {
    stopInvitePoll();
    invitePollRef.current = window.setInterval(async () => {
      try {
        const st = await apiRequest<any>(`/api/pvp/invite/status?invite_code=${encodeURIComponent(code)}`);
        if (st?.status === 'accepted' && st?.match_token) {
          setMatchInfo({
            ok: true,
            match_token: st.match_token,
            stake: st.stake ?? stakeDefault,
            match_duration_sec: st.match_duration_sec ?? matchDurationSec,
            mode: 'invite',
            player1_id: st.player1_id,
            player2_id: st.player2_id,
          });
          setQueueStatus('matched');
          stopInvitePoll();
        }
        if (st?.status === 'expired' || st?.status === 'cancelled') stopInvitePoll();
      } catch {}
    }, 1200);
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

  const startDuel = (mode: DuelMode) => {
    setError('');
    setFinishResponse(null);
    setChallengeFinishResp(null);
    setMyClicks(0);
    setLiveSubmitState('idle');
    stopLivePoll();

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

  const addClicks = (delta: number) => {
    if (screen !== 'duel') return;
    if (duelSecondsLeft <= 0) return;
    setMyClicks((prev) => prev + Math.max(0, delta));
  };

  const onTouchStart = (e: React.TouchEvent) => {
    const delta = Math.min(e.changedTouches?.length || 1, 2);
    addClicks(delta);
  };

  const onMouseDown = () => addClicks(1);

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

          try {
            const me = await apiRequest<any>(`/api/pvp/me?telegram_id=${telegramId}`);
            if (me?.user_id) setMeUserId(me.user_id);
            setMeInfo(me);
          } catch {}
        }
        if (st?.status === 'expired') {
          setError('Session expired');
          stopLivePoll();
        }
      } catch {}
    }, 1200);
  };

  const onLiveSubmit = async () => {
    if (!telegramId) return;
    if (!matchInfo?.match_token) {
      setError('match_token missing');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const res = await apiRequest<any>('/api/pvp/live/submit', {
        method: 'POST',
        body: JSON.stringify({
          telegram_id: telegramId,
          match_token: matchInfo.match_token,
          my_clicks: myClicks,
        }),
      });

      if (res?.status === 'finished') {
        setLiveSubmitState('finished');
        setFinishResponse(res);

        try {
          const me = await apiRequest<any>(`/api/pvp/me?telegram_id=${telegramId}`);
          if (me?.user_id) setMeUserId(me.user_id);
          setMeInfo(me);
        } catch {}
      } else {
        setLiveSubmitState('waiting');
        pollLiveStatus(matchInfo.match_token);
      }
    } catch (e: any) {
      setError(e?.message || 'submit failed');
    } finally {
      setLoading(false);
    }
  };

  // ---- Challenge (как было) ----
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
        body: JSON.stringify({ telegram_id: telegramId, attempt_id: challengeAttemptId, my_clicks: myClicks }),
      });
      setChallengeFinishResp(res);

      try {
        const me = await apiRequest<any>(`/api/pvp/me?telegram_id=${telegramId}`);
        if (me?.user_id) setMeUserId(me.user_id);
        setMeInfo(me);
      } catch {}
    } catch (e: any) {
      setError(e?.message || 'challenge finish failed');
    } finally {
      setLoading(false);
    }
  };

  const resetToLobby = () => {
    stopDuelTimer();
    stopLivePoll();
    setScreen('lobby');
    setMyClicks(0);
    setFinishResponse(null);
    setLiveSubmitState('idle');

    setChallengeFinishResp(null);
    setChallengeAttemptId(null);
    setChallengeOpponent(null);
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

  const onAcceptInviteManual = async () => {
    if (!telegramId) return;
    const code = inviteCode.trim();
    if (!code) return;

    setError('');
    setLoading(true);
    try {
      const data = await apiRequest<any>('/api/pvp/invite/accept', {
        method: 'POST',
        body: JSON.stringify({ telegram_id: telegramId, invite_code: code }),
      });
      setMatchInfo(data);
      if (data?.match_token) {
        setQueueStatus('matched');
        startDuel('live');
      }
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
        body: JSON.stringify({ telegram_id: telegramId, ttl_seconds: 120 }),
      });
      setQueueStatus('waiting');
      startQueuePolling();
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
        body: JSON.stringify({ telegram_id: telegramId }),
      });
      setQueueStatus('idle');
      stopQueuePoll();
    } catch (e: any) {
      setError(e?.message || 'leave failed');
    } finally {
      setLoading(false);
    }
  };

  const isChallenge = duelMode === 'challenge';

  return (
    <div className="px-4 pt-4 text-white">
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
            <div>you: #{meInfo.user_id} @{meInfo.username || '—'}</div>
            <div>victories: {meInfo.pvp_victories ?? 0} | best: {meInfo.pvp_best_result ?? 0}</div>
          </div>
        )}
      </div>

      {screen === 'duel' && (
        <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
          <div className="flex items-start justify-between">
            <div>
              <div className="font-bold text-base">🔥 {isChallenge ? 'Challenge' : 'Duel'}</div>
              {!isChallenge && (
                <div className="text-xs opacity-80">
                  match_token: <span className="font-mono">{matchInfo?.match_token ?? '—'}</span>
                </div>
              )}
            </div>

            <div className="text-right">
              <div className="text-xs opacity-80">Time left</div>
              <div className="text-2xl font-extrabold">{duelSecondsLeft}s</div>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-[#0b1320] border border-[#00f0ff20] p-3">
              <div className="text-xs opacity-70">Your clicks</div>
              <div className="text-2xl font-extrabold">{myClicks}</div>
            </div>

            <div className="rounded-xl bg-[#0b1320] border border-[#00f0ff20] p-3">
              <div className="text-xs opacity-70">Opponent</div>
              <div className="text-sm opacity-90">
                id: <span className="font-mono">{isChallenge ? challengeOpponent?.user_id ?? '—' : computeOpponentUserId() ?? '—'}</span>
              </div>
            </div>
          </div>

          <div className="mt-4">
            <div
              onTouchStart={onTouchStart}
              onMouseDown={onMouseDown}
              className="select-none w-full h-40 rounded-2xl border border-[#00f0ff50] bg-[#0b1320] flex items-center justify-center active:scale-[0.99] shadow-[0_0_18px_#00f0ff20]"
            >
              <div className="text-center">
                <div className="text-2xl font-extrabold">TAP</div>
                <div className="text-xs opacity-70">multitouch up to 2 fingers</div>
              </div>
            </div>
          </div>

          <div className="mt-4 flex gap-2">
            <button onClick={resetToLobby} className="flex-1 rounded-xl bg-[#0b1320] border border-[#00f0ff30] py-2 text-sm">
              Back
            </button>
          </div>
        </div>
      )}

      {screen === 'result' && (
        <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
          <div className="font-bold text-base">🏁 Result</div>

          {duelMode === 'challenge' ? (
            <div className="mt-3">
              <button
                disabled={loading}
                onClick={onChallengeFinish}
                className="w-full rounded-xl bg-[#00f0ff] text-black font-bold py-2 disabled:opacity-60"
              >
                {loading ? 'Loading...' : 'Finish'}
              </button>

              {challengeFinishResp && (
                <div className="mt-3 text-xs whitespace-pre-wrap opacity-90">{JSON.stringify(challengeFinishResp, null, 2)}</div>
              )}
            </div>
          ) : (
            <div className="mt-3">
              <button
                disabled={loading || liveSubmitState === 'finished'}
                onClick={onLiveSubmit}
                className="w-full rounded-xl bg-[#00f0ff] text-black font-bold py-2 disabled:opacity-60"
              >
                {loading ? 'Loading...' : liveSubmitState === 'waiting' ? 'Waiting opponent...' : liveSubmitState === 'finished' ? 'Finished' : 'Submit result'}
              </button>

              {finishResponse && <div className="mt-3 text-xs whitespace-pre-wrap opacity-90">{JSON.stringify(finishResponse, null, 2)}</div>}
            </div>
          )}

          <div className="mt-4 flex gap-2">
            <button onClick={resetToLobby} className="flex-1 rounded-xl bg-[#0b1320] border border-[#00f0ff30] py-2 text-sm">
              Back to lobby
            </button>
          </div>
        </div>
      )}

      {screen === 'lobby' && (
        <div className="mt-4 space-y-4">
          <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
            <div className="flex items-center justify-between">
              <div className="font-bold">🔗 Live duel link</div>
              <div className="text-xs opacity-70">bot: @{BOT_USERNAME}</div>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2">
              <button disabled={loading} onClick={onCreateInvite} className="rounded-xl bg-[#00f0ff] text-black font-bold py-2 disabled:opacity-60">
                Create link
              </button>
              <button
                disabled={loading || !createdInvite?.invite_code}
                onClick={onCancelInvite}
                className="rounded-xl bg-[#0b1320] border border-[#00f0ff30] py-2 text-sm disabled:opacity-60"
              >
                Cancel
              </button>
            </div>

            {createdInvite?.invite_code && (
              <div className="mt-3 rounded-xl bg-[#0b1320] border border-[#00f0ff20] p-3 text-xs">
                <div className="opacity-80">invite_code:</div>
                <div className="font-mono text-sm">{createdInvite.invite_code}</div>

                <div className="mt-2 opacity-80">link:</div>
                <div className="font-mono break-all">{buildInviteLink(createdInvite.invite_code)}</div>

                <div className="mt-2 grid grid-cols-2 gap-2">
                  <button onClick={() => copyText(buildInviteLink(createdInvite.invite_code))} className="rounded-xl bg-[#0b1320] border border-[#00f0ff30] py-2 text-sm">
                    Copy link
                  </button>
                  <button onClick={() => shareInvite(createdInvite.invite_code)} className="rounded-xl bg-[#00f0ff] text-black font-bold py-2">
                    Share
                  </button>
                </div>

                <div className="mt-2 text-[11px] opacity-60">After friend opens the link, match will appear automatically.</div>
              </div>
            )}

            <div className="mt-4 text-xs opacity-80">Manual (fallback): paste invite_code</div>
            <div className="mt-2 flex gap-2">
              <input
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                placeholder="invite_code"
                className="flex-1 rounded-xl bg-[#0b1320] border border-[#00f0ff20] px-3 py-2 text-sm font-mono"
              />
              <button disabled={loading} onClick={onAcceptInviteManual} className="rounded-xl bg-[#00f0ff] text-black font-bold px-4 py-2 disabled:opacity-60">
                Join
              </button>
            </div>
          </div>

          {queueStatus === 'matched' && matchInfo?.match_token && (
            <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
              <div className="font-bold">✅ Match ready</div>
              <div className="mt-2 text-xs opacity-80">
                token: <span className="font-mono">{matchInfo.match_token}</span>
              </div>
              <div className="mt-1 text-xs opacity-80">
                opponent: <span className="font-mono">{computeOpponentUserId() ?? '—'}</span>
              </div>
              <button onClick={() => startDuel('live')} className="mt-3 w-full rounded-xl bg-[#00f0ff] text-black font-bold py-2">
                Start duel
              </button>
            </div>
          )}

          <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
            <div className="font-bold">🎲 Random matchmaking</div>

            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                disabled={loading || queueStatus === 'waiting'}
                onClick={onJoinQueue}
                className="rounded-xl bg-[#00f0ff] text-black font-bold py-2 disabled:opacity-60"
              >
                {queueStatus === 'waiting' ? 'Searching...' : 'Find opponent'}
              </button>
              <button
                disabled={loading || queueStatus !== 'waiting'}
                onClick={onLeaveQueue}
                className="rounded-xl bg-[#0b1320] border border-[#00f0ff30] py-2 text-sm disabled:opacity-60"
              >
                Stop
              </button>
            </div>
          </div>

          <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
            <div className="font-bold">🧱 Challenge</div>
            <div className="mt-1 text-xs opacity-70">Play vs someone’s best result (no stake). Limit: 5/day.</div>

            <button disabled={loading} onClick={onChallengeStart} className="mt-3 w-full rounded-xl bg-[#00f0ff] text-black font-bold py-2 disabled:opacity-60">
              {loading ? 'Loading...' : 'Start challenge'}
            </button>

            {challengeStartResp && <div className="mt-3 text-xs opacity-80 whitespace-pre-wrap">{JSON.stringify(challengeStartResp, null, 2)}</div>}
          </div>
        </div>
      )}
    </div>
  );
};

export default Pvp;
