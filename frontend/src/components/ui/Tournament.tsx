import React, { useEffect, useState } from 'react';
import API_BASE_URL from '../config';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';

interface LeaderboardEntry {
  rank: number;
  telegram_id: number;
  username: string;
  first_name: string;
  last_name: string;
  score: number;
}

const Tournament: React.FC = () => {
  const { t } = useTranslation();
  const [top10, setTop10] = useState<LeaderboardEntry[]>([]);
  const [myRank, setMyRank] = useState<number | null>(null);
  const [myScore, setMyScore] = useState<number>(0);

  useEffect(() => {
    const fetchLeaderboard = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/tournament/leaderboard`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });

        const data = await res.json();
        setTop10(data.top_10);
        setMyRank(data.my_rank ?? null);
        setMyScore(data.my_score ?? 0);
      } catch (err) {
        console.error('Ошибка загрузки турнира:', err);
      }
    };

    fetchLeaderboard();
  }, []);

  const renderName = (entry: LeaderboardEntry) => {
    return entry.username || entry.first_name || `user_${entry.telegram_id}`;
  };

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff]">
      <h2 className="text-xl font-bold text-center drop-shadow-md mb-4">🏆 {t('weekly_tournament')}</h2>
      <p className="text-sm text-center mb-6 text-[#7ee9ff]">{t('top_invites_this_week')}</p>

      <div className="max-w-md mx-auto space-y-2">
        {top10.map((entry) => (
          <div
            key={entry.telegram_id}
            className="flex justify-between items-center bg-[#0e1a2b] px-4 py-2 rounded-xl border border-[#00f0ff40]"
          >
            <span className="font-semibold">#{entry.rank} {renderName(entry)}</span>
            <span className="font-mono text-lg">{entry.score}</span>
          </div>
        ))}
      </div>

      {myRank && myRank > 10 && (
        <div className="mt-8 max-w-md mx-auto bg-[#0e1a2b] px-4 py-3 rounded-xl border border-[#00f0ff40]">
          <p className="text-center font-semibold text-[#7ee9ff]">
            {t('your_place')}: #{myRank} — {myScore} {t('invites')}
          </p>
        </div>
      )}
    </div>
  );
};

export default Tournament;
