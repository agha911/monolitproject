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
      if (data.league) setActiveLeague(data.league);
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
    <div className="min-h-screen bg-[#0B0F1B] text-white px-4 py-6">
      <h2 className="text-2xl font-bold mb-6 text-center tracking-wide">🏆 Həftəlik Turnir</h2>

      {userInfo && (
        <div className="mb-6 p-4 bg-[#111827] rounded-2xl border border-cyan-400 shadow-cyan-500/20 shadow-md">
          <p className="text-sm mb-1">
            <span className="text-gray-400">Liqa:</span> {userInfo.league ? t(userInfo.league) : "—"}
          </p>
          <p className="text-sm mb-1">
            <span className="text-gray-400">Mövqe:</span> {userInfo.rank ?? "—"}
          </p>
          <p className="text-sm">
            <span className="text-gray-400">Qəpik:</span> {userInfo.clicks}
          </p>
        </div>
      )}

      <div className="flex justify-center gap-2 mb-5">
        {leagues.map((league) => (
          <button
            key={league}
            onClick={() => setActiveLeague(league)}
            className={`px-4 py-1.5 rounded-full border text-sm font-medium transition-all duration-150
              ${
                activeLeague === league
                  ? "bg-cyan-400 text-black border-cyan-400 shadow-md shadow-cyan-500/30"
                  : "border-gray-600 text-gray-300 hover:border-cyan-500"
              }`}
          >
            {t(league)}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-center text-gray-400 text-sm">Yüklənir...</p>
      ) : (
        <div className="bg-[#111827] rounded-xl overflow-hidden shadow-md shadow-cyan-800/10">
          {leaderboard.length === 0 ? (
            <p className="text-center py-6 text-gray-400 text-sm">Bu liqada hələ heç kim yoxdur.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="bg-[#1f2937] text-cyan-400 uppercase text-xs">
                <tr>
                  <th className="py-2 px-3">#</th>
                  <th className="py-2 px-3">İstifadəçi</th>
                  <th className="py-2 px-3">Qəpik</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((entry) => (
                  <tr key={entry.rank} className="border-t border-gray-700 hover:bg-gray-800/40 transition">
                    <td className="py-2 px-3">{entry.rank}</td>
                    <td className="py-2 px-3">{entry.username}</td>
                    <td className="py-2 px-3">{entry.clicks}</td>
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

