import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import WebApp from '@twa-dev/sdk';
import API_BASE_URL from '../config';

interface UserEntry {
  id: number;
  username: string;
               total_xp: number;
}

type ReferralStatus = 'open' | 'claimed' | 'expired' | 'none';

interface ReferralBalanceOut {
  day_date: string;
  amount: number;
  status: ReferralStatus;
  expires_at_iso: string;
  seconds_left: number;
}

const Friends: React.FC = () => {
  const { t } = useTranslation();

  const [leaderboard, setLeaderboard] = useState<UserEntry[]>([]);
  const [invitesCount, setInvitesCount] = useState(0);
  const [totalUsers, setTotalUsers] = useState(0);

  const [refBalance, setRefBalance] = useState<ReferralBalanceOut | null>(null);
  const [claimLoading, setClaimLoading] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState<number>(0);
  const timerRef = useRef<number | null>(null);

  const canClaim = useMemo(() => {
    if (!refBalance) return false;
    if (!WebApp?.initData) return false;
    return refBalance.status === 'open' && refBalance.amount > 0 && secondsLeft > 0;
  }, [refBalance, secondsLeft]);

  const fmtTime = (s: number) => {
    const n = Math.max(0, s | 0);
    const hh = String(Math.floor(n / 3600)).padStart(2, '0');
    const mm = String(Math.floor((n % 3600) / 60)).padStart(2, '0');
    const ss = String(n % 60).padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
  };

  const fetchAll = async () => {
    try {
      const [leaderboardRes, invitesRes, usersRes, refBalanceRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/game/leaderboard`),
        fetch(`${API_BASE_URL}/api/user/invites?init_data=${encodeURIComponent(WebApp.initData || '')}`),
        fetch(`${API_BASE_URL}/api/user/count`),
        fetch(`${API_BASE_URL}/api/referral/balance?init_data=${encodeURIComponent(WebApp.initData || '')}`),
      ]);

      const [leaderboardData, invitesData, usersData] = await Promise.all([
        leaderboardRes.json(),
        invitesRes.json(),
        usersRes.json(),
      ]);

      // Разбираем реф. баланс отдельно, чтобы ошибка не уронила всё
      let refBalData: any = null;
      try {
        if (!refBalanceRes.ok) {
          const txt = await refBalanceRes.text().catch(() => '');
          console.error('[referral/balance] HTTP', refBalanceRes.status, txt);
        } else {
          const ct = refBalanceRes.headers.get('content-type') || '';
          if (ct.includes('application/json')) {
            refBalData = await refBalanceRes.json();
          } else {
            const txt = await refBalanceRes.text().catch(() => '');
            console.error('[referral/balance] non-JSON', txt);
          }
        }
      } catch (e) {
        console.error('[referral/balance] fetch/json error', e);
      }

      setLeaderboard(Array.isArray(leaderboardData) ? leaderboardData : (leaderboardData?.items ?? []));
      setInvitesCount(invitesData?.count || 0);
      setTotalUsers(usersData?.count || 0);

      if (refBalData) {
        setRefBalance(refBalData);
        let secs = Number(refBalData.seconds_left ?? 0);
        if ((!secs || secs < 0) && refBalData.expires_at_iso) {
          const end = new Date(refBalData.expires_at_iso).getTime();
          const now = Date.now();
          secs = Math.max(0, Math.floor((end - now) / 1000));
        }
        setSecondsLeft(secs);
      } else {
        setRefBalance({
          day_date: new Date().toISOString().slice(0, 10),
          amount: 0,
          status: 'none',
          expires_at_iso: '',
          seconds_left: 0,
        });
        setSecondsLeft(0);
      }
    } catch (error) {
      console.error('fetchAll error:', error);
    }
  };

  useEffect(() => {
    fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (!refBalance) return;

    // secondsLeft уже установлен в fetchAll; запускаем тиканье
    timerRef.current = window.setInterval(() => {
      setSecondsLeft((s) => (s > 0 ? s - 1 : 0));
    }, 1000) as unknown as number;

    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, [refBalance?.expires_at_iso, refBalance?.seconds_left]);

  const handleInvite = () => {
    const link = `https://t.me/monolit_42_bot?start=${WebApp.initDataUnsafe.user?.id}`;
    const message = encodeURIComponent('Qaqa, Sumqayıta gedirəm, 20 $GAPiyin olmaz?');
    window.open(`https://t.me/share/url?url=${link}&text=${message}`, '_blank');
  };

  const handleClaimReferral = async () => {
  if (!canClaim || claimLoading) return;
  if (!WebApp?.initData) {
    WebApp.showPopup?.({ title: '!', message: t('try_again') as string });
    return;
  }

  // 1) Запоминаем сумму ДО запроса (на случай пустого/не-JSON ответа)
  const preClaimAmount = refBalance?.amount ?? 0;

  try {
    setClaimLoading(true);
    const res = await fetch(`${API_BASE_URL}/api/referral/claim`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // чуть повышаем шанс получить JSON
        'Accept': 'application/json'
      },
      body: JSON.stringify({ init_data: WebApp.initData }),
    });

    let data: any = null;
    let parsed = false;
    try {
      const ct = res.headers.get('content-type') || '';
      if (ct.includes('application/json')) {
        data = await res.json();
        parsed = true;
      } else {
        const txt = await res.text().catch(() => '');
        console.warn('[referral/claim] non-JSON', res.status, txt);
      }
    } catch (e) {
      console.warn('[referral/claim] parse error', e);
    }

    // 2) Если сервер вернул НЕ ok — показываем detail/try_again
    if (!res.ok) {
      WebApp.showPopup?.({
        title: String(res.status),
        message: (data?.detail as string) || (t('try_again') as string),
      });
      return;
    }

    // 3) У нас ok. Если JSON есть — обрабатываем статусы, как обычно
    if (parsed && data && typeof data.status === 'string') {
      const status = data.status;
      if (status === 'ok') {
        await fetchAll();
        WebApp.showPopup?.({
          title: '✓',
          message: `${t('claimed_success')}: +${data.claimed_amount} $GAP`,
        });
      } else if (status === 'expired') {
        WebApp.showPopup?.({ title: '!', message: t('expired') as string });
        await fetchAll();
      } else if (status === 'nothing') {
        WebApp.showPopup?.({ title: '!', message: t('nothing_to_claim') as string });
      } else {
        console.warn('[referral/claim] unexpected payload', data);
        WebApp.showPopup?.({ title: '!', message: t('try_again') as string });
      }
      return;
    }

    // 4) ФОЛЛБЭК: ok, но JSON нет/неожидан. Считаем клейм успешным.
    // Показываем, что собрали то, что было на экране до клика:
    await fetchAll();
    WebApp.showPopup?.({
      title: '✓',
      message: `${t('claimed_success')}: +${preClaimAmount} $GAP`,
    });

  } catch (e) {
    console.error('[referral/claim] fetch failed', e);
    WebApp.showPopup?.({ title: '!', message: t('try_again') as string });
  } finally {
    setClaimLoading(false);
  }
};

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff] flex flex-col gap-8">
      <h2 className="text-xl font-bold text-center drop-shadow">👥 {t('title_friends')}</h2>

      <div className="bg-[#0e1a2b] p-4 rounded shadow-lg border border-[#00f0ff30] text-center flex flex-col gap-3">
        <p className="text-lg">{t('invited_friends')}: {invitesCount}</p>
        <button
          onClick={handleInvite}
          className="bg-[#00f0ff] text-[#131f2f] font-bold py-2 px-6 rounded hover:bg-[#7ee9ff]"
        >
          {t('invite_friends')}
        </button>
      </div>

      {/* Реферальный блок можно скрывать, если нет приглашённых */}
      <div className="bg-[#0e1a2b] p-4 rounded shadow-lg border border-[#00f0ff30]">
        <div className="flex items-center justify-between mb-3">
          <div className="flex flex-col">
            <span className="text-lg font-semibold">{t('ref_balance')}</span>
            <span className="text-sm text-[#7ee9ff]">
              {t('status')}: {refBalance?.status ?? '—'}
            </span>
            {!WebApp?.initData && (
              <span className="text-xs text-[#ffadad] mt-1">
                {/* добавь ключ в локали при желании */}
                Telegram initData is missing
              </span>
            )}
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold">{refBalance?.amount ?? 0} $GAP</div>
            <div className="text-xs text-[#7ee9ff]">
              {t('resets_in')}: {fmtTime(secondsLeft)}
            </div>
          </div>
        </div>

        <button
          onClick={handleClaimReferral}
          disabled={!canClaim || claimLoading}
          className={`w-full font-bold py-2 px-6 rounded transition
            ${canClaim && !claimLoading
              ? 'bg-[#00f0ff] text-[#131f2f] hover:bg-[#7ee9ff]'
              : 'bg-[#0d273d] text-[#7ee9ff80] cursor-not-allowed'
            }`}
        >
          {claimLoading ? t('processing') : t('claim_reward')}
        </button>
      </div>

      <p className="text-center text-[#7ee9ff] text-sm">
        👥 {t('total_users')}: {totalUsers}
      </p>

      <div className="overflow-x-auto">
        <table className="min-w-full border border-[#00f0ff30] text-sm bg-[#0e1a2b] rounded-lg shadow-[0_0_10px_#00f0ff20] overflow-hidden">
          <thead className="bg-[#0d273d] text-[#7ee9ff]">
            <tr>
              <th className="px-4 py-2 border border-[#00f0ff20]">#</th>
              <th className="px-4 py-2 border border-[#00f0ff20]">{t('user')}</th>
              <th className="px-4 py-2 border border-[#00f0ff20]">$GAP</th>
            </tr>
          </thead>
          <tbody>
            {leaderboard.map((user, index) => (
              <tr
                key={user.id}
                className={`text-center ${
                  index === 0 ? 'bg-[#001d2b] font-bold text-[#00f0ff]' : 'text-[#a0f6ff] hover:bg-[#0f273c]'
                }`}
              >
                <td className="px-4 py-2 border border-[#00f0ff10]">{index + 1}</td>
                <td className="px-4 py-2 border border-[#00f0ff10]">
                  {user.username
                    ? (user.username.startsWith('@') ? user.username : `@${user.username}`)
                    : `user_${user.id}`}
                </td>
                <td className="px-4 py-2 border border-[#00f0ff10]">{user.total_xp}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Friends;





