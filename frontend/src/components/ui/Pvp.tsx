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
      } catch {
        // fallback legacy
      }

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

  const startDuel = (mode: DuelMode) => {
    setError('');
    setFinishResponse(null);
    setChallengeFinishResp(null);

    stopPrepTimer();
    stopDuelTimer();
    stopLivePoll();

    setDuelMode(mode);
    setScreen('duel'); // ✅ теперь duel — отдельный экран
    setPhase('prep');
    setMyClicks(0);
    setPrepSecondsLeft(PREP_SECONDS);
    setDuelSecondsLeft(matchDurationSec);
    setLiveSubmitState('idle');

    startPrepCountdown();
  };

  const onTap = () => {
    if (screen !== 'duel') return;
    if (phase !== 'active') return;
    setMyClicks((v) => v + 1);
  };

  const startInvitePolling = (inviteCode: string) => {
    stopInvitePoll();
    invitePollRef.current = window.setInterval(async () => {
      if (!telegramId) return;
      try {
        const st = await apiRequest<any>(`/api/pvp/invite/status?invite_code=${encodeURIComponent(inviteCode)}`);
        if (st?.status === 'accepted' && st?.match_token) {
          setMatchInfo(st);
          stopInvitePoll();
          startDuel('live'); // ✅ уводит на отдельный duel экран
        }
        if (st?.status === 'expired') {
          setError(t('pvp_invite_expired', { defaultValue: 'Dəvət linkinin vaxtı bitdi' }));
          stopInvitePoll();
        }
        if (st?.status === 'cancelled') {
          setError(t('pvp_invite_cancelled', { defaultValue: 'Dəvət ləğv edildi' }));
          stopInvitePoll();
        }
      } catch {}
    }, 900);
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
          setScreen('result'); // ✅ отдельный экран результата
        }

        if (st?.status === 'expired') {
          setError(t('pvp_session_expired', { defaultValue: 'Sessiyanın vaxtı bitdi' }));
          stopLivePoll();
          setScreen('result');
        }
      } catch {}
    }, 900);
  };

  const onLiveSubmit = async () => {
    if (!telegramId) return;
    if (!matchInfo?.match_token) {
      setError(t('pvp_error_match_token_missing', { defaultValue: 'match_token tapılmadı' }));
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
        await refreshMe();
        await refreshWeekly();
        setScreen('result');
      } else {
        setLiveSubmitState('waiting');
        pollLiveStatus(matchInfo.match_token);
      }
    } catch (e: any) {
      setError(e?.message || t('pvp_error_submit_failed', { defaultValue: 'Göndərmə xətası' }));
    } finally {
      setLoading(false);
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
      setChallengeStartResp(res);
      setChallengeAttemptId(res?.attempt_id ?? null);
      setChallengeOpponent(res?.opponent ?? null);
      startDuel('challenge'); // ✅ отдельный экран
    } catch (e: any) {
      setError(e?.message || t('pvp_error_challenge_start_failed', { defaultValue: 'Challenge başlatmaq alınmadı' }));
    } finally {
      setLoading(false);
    }
  };

  const onChallengeFinish = async () => {
    if (!telegramId) return;
    if (!challengeAttemptId) {
      setError(t('pvp_error_attempt_id_missing', { defaultValue: 'attempt_id tapılmadı' }));
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
      await refreshMe();
      await refreshWeekly();
      setScreen('result'); // ✅ отдельный экран результата
    } catch (e: any) {
      setError(e?.message || t('pvp_error_challenge_finish_failed', { defaultValue: 'Challenge bitirmək alınmadı' }));
    } finally {
      setLoading(false);
    }
  };

  const resetToLobby = () => {
    stopPrepTimer();
    stopDuelTimer();
    stopLivePoll();

    setScreen('lobby'); // ✅ возвращаем на lobby
    setMyClicks(0);
    setFinishResponse(null);
    setLiveSubmitState('idle');

    setChallengeFinishResp(null);
    setChallengeAttemptId(null);
    setChallengeOpponent(null);

    setPhase('prep');
    setPrepSecondsLeft(0);
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
      setError(e?.message || t('pvp_error_invite_create_failed', { defaultValue: 'Dəvət yaratmaq alınmadı' }));
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
      setCreatedInvite(null);
      stopInvitePoll();
    } catch (e: any) {
      setError(e?.message || t('pvp_cancel_invite', { defaultValue: 'Dəvəti ləğv et' }));
    } finally {
      setLoading(false);
    }
  };

  const isChallenge = duelMode === 'challenge';
  const victories = pickVictories(meInfo);
  const best = pickBest(meInfo);

  const opponentUserId = computeOpponentUserId();
  const inviteUrl = createdInvite?.invite_code ? buildInviteLink(createdInvite.invite_code) : '';

  // ✅ ВАЖНО: теперь рендер идёт “по экранам”, чтобы ничего не смешивалось.
  return (
    <div className="min-h-screen bg-[#07111e] px-4 pt-4 pb-24 text-white">
      {/* ==== DUEL SCREEN (отдельно) ==== */}
      {screen === 'duel' && (
        <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4 shadow-[0_0_12px_#00f0ff20]">
          <div className="flex items-start justify-between">
            <div>
              <div className="font-bold text-base">
                🔥{' '}
                {isChallenge
                  ? t('pvp_challenge_title', { defaultValue: 'Challenge' })
                  : t('pvp_duel', { defaultValue: 'Duel' })}
              </div>
              {!isChallenge && (
                <div className="text-xs opacity-80">
                  {t('pvp_match_token', { defaultValue: 'match_token:' })}{' '}
                  <span className="font-mono">{matchInfo?.match_token ?? '—'}</span>
                </div>
              )}
              {error && <div className="mt-2 text-xs text-[#ffadad] whitespace-pre-wrap">{error}</div>}
            </div>

            <div className="text-right">
              <div className="text-xs opacity-80">
                {phase === 'prep'
                  ? t('pvp_starting_in', { defaultValue: 'Başlanır' })
                  : t('pvp_time_left', { defaultValue: 'Vaxt qalıb' })}
              </div>
              <div className="text-2xl font-extrabold">
                {phase === 'prep' ? `${prepSecondsLeft}s` : `${duelSecondsLeft}s`}
              </div>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-[#0b1320] border border-[#00f0ff20] p-3">
              <div className="text-xs opacity-70">{t('pvp_your_clicks', { defaultValue: 'Sənin kliklərin' })}</div>
              <div className="text-2xl font-extrabold">{myClicks}</div>
            </div>

            <div className="rounded-xl bg-[#0b1320] border border-[#00f0ff20] p-3">
              <div className="text-xs opacity-70">{t('pvp_opponent', { defaultValue: 'Rəqib' })}</div>
              <div className="text-2xl font-extrabold">{opponentUserId ?? '—'}</div>
            </div>
          </div>

          <div
            className="mt-3 rounded-2xl bg-[#0b1320] border border-[#00f0ff20] p-5 text-center select-none"
            onPointerDown={onTap}
            style={{ touchAction: 'manipulation' }}
          >
            <div className="text-xs opacity-70">{t('pvp_tap', { defaultValue: 'Toxun' })}</div>
            <div className="text-3xl font-extrabold">+1</div>
            {phase === 'prep' ? (
              <div className="mt-3 text-xs opacity-70">{t('pvp_wait_start', { defaultValue: 'Başlanğıcı gözlə…' })}</div>
            ) : (
              <div className="mt-3 text-xs opacity-70">{t('pvp_go', { defaultValue: 'Başla!' })}</div>
            )}
          </div>

          {phase === 'prep' && (
            <div className="mt-4 flex items-center justify-center">
              <div className="rounded-2xl bg-black/60 border border-white/20 px-6 py-4 text-center">
                <div className="text-sm opacity-90">{t('pvp_get_ready', { defaultValue: 'Hazır ol' })}</div>
                <div className="text-3xl font-bold">{prepSecondsLeft}</div>
              </div>
            </div>
          )}

          <div className="mt-4 space-y-2">
            {!isChallenge ? (
              <button
                className="w-full rounded-xl bg-[#00f0ff] text-black font-bold py-2 disabled:opacity-60"
                onClick={onLiveSubmit}
                disabled={loading || liveSubmitState !== 'idle'}
              >
                {liveSubmitState === 'idle'
                  ? t('submit', { defaultValue: 'Göndər' })
                  : t('waiting', { defaultValue: 'Gözlənilir…' })}
              </button>
            ) : (
              <button
                className="w-full rounded-xl bg-[#00f0ff] text-black font-bold py-2 disabled:opacity-60"
                onClick={onChallengeFinish}
                disabled={loading}
              >
                {t('finish', { defaultValue: 'Bitir' })}
              </button>
            )}

            <button className="w-full rounded-xl bg-white/10 border border-white/10 py-2" onClick={resetToLobby}>
              {t('back', { defaultValue: 'Geri' })}
            </button>
          </div>
        </div>
      )}

      {/* ==== RESULT SCREEN (отдельно) ==== */}
      {screen === 'result' && (
        <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4 shadow-[0_0_12px_#00f0ff20]">
          <div className="font-bold text-base">{t('result', { defaultValue: 'Nəticə' })}</div>
          {error && <div className="mt-2 text-xs text-[#ffadad] whitespace-pre-wrap">{error}</div>}

          <div className="mt-2 text-xs opacity-80 whitespace-pre-wrap">
            {!isChallenge ? JSON.stringify(finishResponse, null, 2) : JSON.stringify(challengeFinishResp, null, 2)}
          </div>

          <button className="mt-3 w-full rounded-xl bg-[#00f0ff] text-black font-bold py-2" onClick={resetToLobby}>
            {t('pvp_back_to_lobby', { defaultValue: 'Lobbiyə qayıt' })}
          </button>
        </div>
      )}

      {/* ==== LOBBY SCREEN (таблица + кнопки) ==== */}
      {screen === 'lobby' && (
        <>
          {/* Header */}
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

          {/* Weekly leaderboard (только в lobby) */}
          <div className="mt-4 rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4 shadow-[0_0_12px_#00f0ff20]">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold">
                🏆 {t('pvp_weekly_leaderboard', { defaultValue: 'Weekly leaderboard' })}
              </div>
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
                    • {t('pvp_time_left', { defaultValue: 'Vaxt qalıb' })}:{' '}
                    <span className="font-mono">{new Date(weeklySeason.end_at).toLocaleString()}</span>
                  </>
                ) : null}
              </div>
            )}

            {weeklyItems.length === 0 ? (
              <div className="mt-3 text-xs opacity-70">
                {t('pvp_no_leaderboard', { defaultValue: 'Hələlik məlumat yoxdur.' })}
              </div>
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

          {/* Lobby actions */}
          <div className="mt-4 space-y-3">
            <div className="rounded-2xl bg-[#0e1a2b] border border-[#00f0ff40] p-4">
              <div className="font-bold">{t('pvp_live_duel', { defaultValue: 'Canlı duel' })}</div>
              <div className="mt-2 text-xs opacity-80">
                {t('pvp_live_hint', { defaultValue: 'Dəvət linki yarat və rəqibinə göndər.' })}
              </div>

              <div className="mt-3 space-y-2">
                <button
                  className="rounded-xl bg-[#00f0ff] text-black font-bold py-2 w-full disabled:opacity-60"
                  onClick={onCreateInvite}
                  disabled={!canUse || loading}
                >
                  {t('pvp_create_invite', { defaultValue: 'Dəvət yarat' })}
                </button>

                {createdInvite?.invite_code && (
                  <div className="rounded-xl bg-[#0b1320] border border-[#00f0ff20] p-3 text-xs">
                    <div className="opacity-80">{t('pvp_invite_code', { defaultValue: 'Dəvət kodu:' })}</div>
                    <div className="font-mono break-all">{createdInvite.invite_code}</div>

                    <div className="mt-2 opacity-80">{t('pvp_link', { defaultValue: 'Link:' })}</div>
                    <div className="font-mono break-all">{inviteUrl}</div>

                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <button
                        className="rounded-xl bg-white/10 border border-white/10 py-2"
                        onClick={() => {
                          try {
                            WebApp.openTelegramLink(inviteUrl);
                          } catch {}
                        }}
                      >
                        {t('open', { defaultValue: 'Aç' })}
                      </button>
                      <button
                        className="rounded-xl bg-white/10 border border-white/10 py-2"
                        onClick={() => {
                          const share = buildShareLink(
                            inviteUrl,
                            t('pvp_share_text', { defaultValue: 'Mənim duel’uma qoşul!' })
                          );
                          try {
                            WebApp.openTelegramLink(share);
                          } catch {}
                        }}
                      >
                        {t('share', { defaultValue: 'Paylaş' })}
                      </button>
                    </div>

                    <button
                      className="mt-2 w-full rounded-xl bg-white/10 border border-white/10 py-2"
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
                {t('pvp_challenge_hint', {
                  defaultValue: 'Rəqibin best_result nəticəsinə qarşı oyna. Qələbə +1 victory verir.',
                })}
              </div>

              <button
                className="mt-3 rounded-xl bg-[#00f0ff] text-black font-bold py-2 w-full disabled:opacity-60"
                onClick={onChallengeStart}
                disabled={!canUse || loading}
              >
                {t('pvp_start_challenge', { defaultValue: 'Challenge başlat' })}
              </button>

              {challengeStartResp?.ok && challengeOpponent && (
                <div className="mt-3 rounded-xl bg-[#0b1320] border border-[#00f0ff20] p-3 text-xs">
                  <div className="opacity-80">{t('pvp_opponent_colon', { defaultValue: 'Rəqib:' })}</div>
                  <div className="mt-1">
                    #{challengeOpponent.user_id} @{challengeOpponent.username || '—'}
                  </div>
                  <div className="mt-1">
                    {t('pvp_best_colon', { defaultValue: 'best:' })}{' '}
                    <span className="font-mono">{intOrZero(challengeOpponent.best_result)}</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default Pvp;
