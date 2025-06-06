import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface UserEntry {
  id: number;
  username: string;
  total_xp: number;
}

const Friends: React.FC = () => {
  const { t } = useTranslation();
  const [leaderboard, setLeaderboard] = useState<UserEntry[]>([]);

  useEffect(() => {
    const fetchLeaderboard = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/game/leaderboard');
        const data = await res.json();
        setLeaderboard(data);
      } catch (error) {
        console.error('Ошибка загрузки рейтинга:', error);
      }
    };

    fetchLeaderboard();
  }, []);

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff]">
      <h2 className="text-xl font-bold text-center drop-shadow mb-6">🏆 {t('title_friends')}</h2>

      {leaderboard.length === 0 ? (
        <p className="text-center text-[#7ee9ff]">{t('no_data')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full border border-[#00f0ff30] text-sm bg-[#0e1a2b] rounded-lg shadow-[0_0_10px_#00f0ff20] overflow-hidden">
            <thead className="bg-[#0d273d] text-[#7ee9ff]">
              <tr>
                <th className="px-4 py-2 border border-[#00f0ff20]">#</th>
                <th className="px-4 py-2 border border-[#00f0ff20]">{t('user')}</th>
                <th className="px-4 py-2 border border-[#00f0ff20]">$MONO</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((user, index) => (
                <tr
                  key={user.id}
                  className={`text-center ${
                    index === 0
                      ? 'bg-[#001d2b] font-bold text-[#00f0ff]'
                      : 'text-[#a0f6ff] hover:bg-[#0f273c]'
                  }`}
                >
                  <td className="px-4 py-2 border border-[#00f0ff10]">{index + 1}</td>
                  <td className="px-4 py-2 border border-[#00f0ff10]">@{user.username}</td>
                  <td className="px-4 py-2 border border-[#00f0ff10]">{user.total_xp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default Friends;

