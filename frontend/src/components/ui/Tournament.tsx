import React, { useEffect, useState } from "react";
import API_BASE_URL from "../config";
import { useTranslation } from "react-i18next";

interface LeaderboardEntry {
  username: string;
  clicks: number;
  rank: number;
}

interface UserTournamentInfo {
  league: "bronze" | "silver" | "gold" | null;
  rank: number | null;
  clicks: number;
}

const leagues = ["bronze", "silver", "gold"] as const;

export default function Tournament() {
  const { t } = useTranslation();
  const [activeLeague, setActiveLeague] = useState<"bronze" | "silver" | "gold">("bronze");
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [userInfo, setUserInfo] = useState<UserTournamentInfo | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchUserInfo();
  }, []);

  useEffect(() => {
    fetchLeaderboard(activeLeague);
  }, [activeLeague]);

  const fetchUserInfo = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/tournament/me`, {
        headers: { "init-data": window?.Telegram?.WebApp?.initData || "" },
      });
      const data = await res.json();
      setUserInfo(data);

      if (data.league) {
        setActiveLeague(data.league);
      }
    } catch (err) {
      console.error("Failed to fetch user info:", err);
    }
  };

  const fetchLeaderboard = async (league: string) => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE_URL}/api/tournament/leaderboard?league=${league}`);
      const data = await res.json();
      setLeaderboard(data);
    } catch (err) {
      console.error("Failed to fetch leaderboard:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4">
      <h2 className="text-xl font-bold mb-4 text-center">🏆 Həftəlik Turnir</h2>

      {userInfo && (
        <div className="mb-4 p-3 bg-gray-800 rounded-xl text-white text-sm">
          <p><strong>Liqa:</strong> {userInfo.league ? t(userInfo.league) : "—"}</p>
          <p><strong>Mövqe:</strong> {userInfo.rank ?? "—"}</p>
          <p><strong>Toplanmış qəpik:</strong> {userInfo.clicks}</p>
        </div>
      )}

      <div className="flex justify-center mb-4">
        {leagues.map((league) => (
          <button
            key={league}
            onClick={() => setActiveLeague(league)}
            className={`px-3 py-1 mx-1 rounded-full text-sm ${
              activeLeague === league ? "bg-yellow-400 text-black font-bold" : "bg-gray-700 text-white"
            }`}
          >
            {t(league)}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-center text-sm text-gray-400">Yüklənir...</p>
      ) : (
        <div className="bg-gray-900 rounded-xl p-3 text-white text-sm">
          {leaderboard.length === 0 ? (
            <p className="text-center">Bu liqada hələ heç kim yoxdur.</p>
          ) : (
            <table className="w-full text-left">
              <thead>
                <tr>
                  <th>#</th>
                  <th>İstifadəçi</th>
                  <th>Qəpik</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((entry) => (
                  <tr key={entry.rank} className="border-t border-gray-700">
                    <td className="py-1">{entry.rank}</td>
                    <td className="py-1">{entry.username}</td>
                    <td className="py-1">{entry.clicks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
