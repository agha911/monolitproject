import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import WebApp from '@twa-dev/sdk';
import API_BASE_URL from '../config';

interface UserEntry {
  id: number;
  username: string;
  total_xp: number;
}

const Friends: React.FC = () => {
  const { t } = useTranslation();
  const [leaderboard, setLeaderboard] = useState<UserEntry[]>([]);
  const [invitesCount, setInvitesCount] = useState(0);
  const [totalUsers, setTotalUsers] = useState(0);

  const fetchData = async () => {
    try {
      const [leaderboardRes, invitesRes, usersRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/game/leaderboard`),
        fetch(`${API_BASE_URL}/api/user/invites?init_data=${encodeURIComponent(WebApp.initData)}`),
        fetch(`${API_BASE_URL}/api/user/count`)
      ]);

      const leaderboardData = await leaderboardRes.json();
      const invitesData = await invitesRes.json();
      const usersData = await usersRes.json();

      setLeaderboard(leaderboardData);
      setInvitesCount(invitesData.count || 0);
      setTotalUsers(usersData.count || 0);
    } catch (error) {
      console.error('Ошибка загрузки данных:', error);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    const onFocus = () => {
      if (document.visibilityState === 'visible') {
        fetchData();
      }
    };

    document.addEventListener('visibilitychange', onFocus);
    return () => document.removeEventListener('visibilitychange', onFocus);
  }, []);

  const handleInvite = () => {
    const inviterId = WebApp.initDataUnsafe?.user?.id;
    if (!inviterId) return;
    const link = `https://t.me/monolit_42_bot?start=${inviterId}`;
    const message = encodeURIComponent("Qaqa, Sumqayıta gedirəm, 20 $GAPiyin olmaz?");
    window.open(`https://t.me/share/url?url=${link}&text=${message}`, '_blank');
  };

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff] flex flex-col gap-8">
      <h2 className="text-xl font-bold text-center drop-shadow">👥 {t('title_friends')}</h2>

      <div className="bg-[#0e1a2b] p-4 rounded shadow-lg border border-[#00f0ff30] text-center">
        <p className="text-lg mb-2">{t('invited_friends')}: {invitesCount}</p>
        <p className="text-base mb-4">💰 {t('reward')}: {invitesCount * 200} $GAP</p>
        <button
          onClick={handleInvite}
          className="bg-[#00f0ff] text-[#131f2f] font-bold py-2 px-6 rounded hover:bg-[#7ee9ff] mb-2"
        >
          {t('invite_friends')}
        </button>
        <button
          onClick={fetchData}
          className="text-xs text-[#7ee9ff] underline mt-2"
        >
          {t('refresh')}
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
                className={\`text-center \${index === 0
                  ? 'bg-[#001d2b] font-bold text-[#00f0ff]'
                  : 'text-[#a0f6ff] hover:bg-[#0f273c]'}\`}
              >
                <td className="px-4 py-2 border border-[#00f0ff10]">{index + 1}</td>
                <td className="px-4 py-2 border border-[#00f0ff10]">
                  {user.username
                    ? (user.username.startsWith('@') ? user.username : \`@\${user.username}\`)
                    : \`user_\${user.id}\`}
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

