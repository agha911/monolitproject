import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import WebApp from '@twa-dev/sdk';
import API_BASE_URL from '../config';

type ApiOk<T> = T & { ok: boolean };

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

const Pvp: React.FC = () => {
  const { t } = useTranslation();

  const telegramId = useMemo(() => getTelegramId(), []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  const [config, setConfig] = useState<any>(null);

  // invite create / accept
  const [inviteCode, setInviteCode] = useState('');
  const [createdInvite, setCreatedInvite] = useState<any>(null);
  const [acceptedInvite, setAcceptedInvite] = useState<any>(null);

  // matchmaking
  const [queueStatus, setQueueStatus] = useState<'idle' | 'waiting' | 'matched'>('idle');
  const [matchInfo, setMatchInfo] = useState<any>(null);
  const pollTimerRef = useRef<number | null>(null);

  const canUse = !!telegramId && !!WebApp.initData;

  useEffect(() => {
    // best effort: подгружаем config (если эндпоинт есть)
    (async () => {
      try {
        const cfg = await apiRequest<any>('/api/pvp/config');
        setConfig(cfg);
      } catch {
        // config может не существовать — не критично
      }
    })();

    return () => {
      if (pollTimerRef.current) window.clearInterval(pollTimerRef.current);
    };
  }, []);

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
        // не спамим ошибками, просто покажем 1 раз
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
      setMatchInfo(data); // на случай если accept возвращает match_token и expires_at
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
            <div>stake: {config?.stake_default ?? 50000}</div>
            <div>duration: {config?.match_duration_sec ?? 30}s</div>
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
          <div className="text-sm opacity-80 mb-2">
            {t('pvp_enter_code', { defaultValue: 'Enter invite code' })}
          </div>

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
                <div>expires_at: <span className="font-mono">{acceptedInvite.expires_at}</span></div>
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
            <div className="text-sm opacity-80">
              {t('pvp_waiting', { defaultValue: 'Searching…' })}
            </div>
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
                <div>expires_at: <span className="font-mono">{matchInfo.expires_at}</span></div>
              ) : null}
              {matchInfo.match_duration_sec ? (
                <div>duration: {matchInfo.match_duration_sec}s</div>
              ) : null}
            </div>

            <div className="mt-2 text-xs opacity-70">
              {/* Следующим шагом сделаем реальный экран матча и finish */}
              Next: start duel screen + timer + clicks + finish.
            </div>
          </div>
        )}
      </div>

      {/* Debug/info */}
      <div className="mt-4 text-xs opacity-60">
        telegram_id: {telegramId ?? '—'}
      </div>
    </div>
  );
};

export default Pvp;
