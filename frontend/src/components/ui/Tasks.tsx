import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from '../config';
import WebApp from '@twa-dev/sdk';

const Tasks: React.FC = () => {
  const { t } = useTranslation();
  const telegramUser = WebApp.initDataUnsafe?.user;
  const telegramUserId = telegramUser?.id;

  const [completed, setCompleted] = useState(false);
  const [message, setMessage] = useState('');
  const [openedInstagram, setOpenedInstagram] = useState(false);

  const [streak, setStreak] = useState<number | null>(null);
  const [reward, setReward] = useState<number | null>(null);
  const [checkedIn, setCheckedIn] = useState(false);
  const [checkinMessage, setCheckinMessage] = useState('');

  const handleInstagramClick = () => {
    window.open('https://www.instagram.com/gap_pick', '_blank');
    setOpenedInstagram(true);
  };

  const handleComplete = async () => {
    if (!telegramUserId) {
      setMessage('Ошибка: пользователь не определён');
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/task/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: telegramUserId,
          task_id: 'follow_instagram',
        }),
      });

      const data = await res.json();
      if (data.status === 'success') {
        setCompleted(true);
        setMessage(t('reward_received', { amount: data.reward }));
      } else if (data.status === 'already_completed') {
        setMessage(t('already_done'));
        setCompleted(true);
      } else {
        setMessage(t('error'));
      }
    } catch (error) {
      setMessage(t('error'));
    }
  };

  const handleCheckIn = async () => {
    if (!telegramUserId) {
      setCheckinMessage('Ошибка: пользователь не определён');
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/task/daily_checkin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: telegramUserId }),
      });

      const data = await res.json();

      if (data.status === 'success') {
        setStreak(data.day);
        setReward(data.reward);
        setCheckedIn(true);
        setCheckinMessage(`🎉 ${t('reward_received', { amount: data.reward })}`);
      } else if (data.status === 'already_checked_in') {
        setStreak(data.day);
        setReward(data.reward);
        setCheckedIn(true);
        setCheckinMessage(`✅ ${t('checkin_already')}`);
      } else {
        setCheckinMessage(t('error'));
      }
    } catch (err) {
      setCheckinMessage(t('error'));
    }
  };

  const rewards = [10, 20, 30, 40, 50, 60, 70];

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff] space-y-6">
      <h2 className="text-xl font-bold text-center drop-shadow-md">📋 {t('title_tasks')}</h2>

      {/* Instagram подписка */}
      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff20] space-y-2 text-center">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">{t('subscribe_instagram')}</h3>
        <a
          href="https://www.instagram.com/gap_pick"
          target="_blank"
          rel="noreferrer"
          className="text-[#00f0ff] underline"
        >
          @gap_pick
        </a>
        <p className="text-sm text-[#a0f6ff]">{t('reward_received', { amount: 1000 })}</p>

        {!openedInstagram ? (
          <button
            onClick={handleInstagramClick}
            className="bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all"
          >
            {t('go_to_instagram')}
          </button>
        ) : (
          <button
            onClick={handleComplete}
            disabled={completed}
            className="bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all disabled:opacity-40"
          >
            {completed ? t('already_done') : t('i_subscribed')}
          </button>
        )}

        {message && <p className="text-sm mt-2 text-[#a0f6ff]">{message}</p>}
      </div>

      {/* Ежедневный чек-ин */}
      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff20] space-y-2 text-center">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">{t('daily_checkin')}</h3>
        <p className="text-sm text-[#a0f6ff]">{t('checkin_get')}</p>

        <div className="flex justify-center gap-2">
          {rewards.map((r, index) => (
            <div
              key={index}
              className={`w-10 h-10 flex items-center justify-center rounded-full text-xs font-bold transition ${
                streak && index < streak
                  ? 'bg-[#00f0ff] text-[#0e1a2b]'
                  : 'bg-[#1e2e3d] text-[#7ee9ff]'
              }`}
            >
              {r}
            </div>
          ))}
        </div>

        <button
          onClick={handleCheckIn}
          disabled={checkedIn}
          className="mt-4 bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all disabled:opacity-40"
        >
          {checkedIn ? t('checkin_already') : t('checkin_get')}
        </button>

        {checkinMessage && <p className="text-sm mt-2 text-[#a0f6ff]">{checkinMessage}</p>}
      </div>
    </div>
  );
};

export default Tasks;





