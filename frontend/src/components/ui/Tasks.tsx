import React, { useState, useEffect } from 'react';
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

  const [joined, setJoined] = useState(false);
  const [groupMessage, setGroupMessage] = useState('');
  const [openedGroup, setOpenedGroup] = useState(false);

  const [streak, setStreak] = useState<number | null>(null);
  const [reward, setReward] = useState<number | null>(null);
  const [checkedIn, setCheckedIn] = useState(false);
  const [checkinMessage, setCheckinMessage] = useState('');

  const [dailyTarget, setDailyTarget] = useState<number | null>(null);
  const [dailyProgress, setDailyProgress] = useState<number | null>(null);
  const [dailyCompleted, setDailyCompleted] = useState<boolean>(false);

  // Загрузка ежедневной задачи
  const fetchDailyTask = async () => {
    if (!telegramUserId) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/task/daily`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: telegramUserId }),
      });

      const data = await res.json();
      if (data.status === 'ok') {
        setDailyTarget(data.daily_target);
        setDailyProgress(data.daily_progress);
        setDailyCompleted(data.daily_completed);
      }
    } catch (err) {
      console.error('Ошибка при загрузке ежедневной задачи', err);
    }
  };

  useEffect(() => {
    fetchDailyTask();
  }, [telegramUserId]);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchDailyTask();
    }, 10000);
    return () => clearInterval(interval);
  }, [telegramUserId]);

  const handleInstagramClick = () => {
    window.open('https://www.instagram.com/gap_pick', '_blank');
    setOpenedInstagram(true);
  };

  const handleGroupClick = () => {
    window.open('https://t.me/+h-VjXbnz0BI2OGI6', '_blank');
    setOpenedGroup(true);
  };

  const handleComplete = async (task_id: string, setter: any, msgSetter: any) => {
    if (!telegramUserId) {
      msgSetter('Ошибка: пользователь не определён');
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/task/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: telegramUserId, task_id }),
      });

      const data = await res.json();
      if (data.status === 'success') {
        setter(true);
        msgSetter(t('reward_received', { amount: data.reward }));
      } else if (data.status === 'already_completed') {
        setter(true);
        msgSetter(t('already_done'));
      } else {
        msgSetter(t('error'));
      }
    } catch (error) {
      msgSetter(t('error'));
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

  const handleShare = () => {
    WebApp.shareLink?.({
      url: 'https://t.me/gap_pick_bot?start=from_task',
      text: t('share_message_text'),
    });
  };

  const rewards = [100, 200, 300, 400, 500, 600, 700];

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff] space-y-6">
      <h2 className="text-xl font-bold text-center drop-shadow-md">📋 {t('title_tasks')}</h2>

      {/* ... Instagram и группа (не изменено) ... */}

      {/* Ежедневная задача на клики */}
      {dailyTarget !== null && dailyProgress !== null && (
        <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff20] space-y-4 text-center">
          <h3 className="text-lg font-semibold text-[#7ee9ff]">{t('daily_task_clicker')}</h3>
          <div className="w-full h-4 bg-[#1e2e3d] rounded-full overflow-hidden">
            <div
              className="h-full bg-[#00f0ff] transition-all"
              style={{ width: `${Math.min((dailyProgress / dailyTarget) * 100, 100)}%` }}
            ></div>
          </div>
          <p className="text-sm text-[#a0f6ff]">
            {t('daily_task_goal')}: {dailyProgress} / {dailyTarget}
          </p>
          {dailyCompleted ? (
            <>
              <p className="text-green-400 text-sm font-semibold">{t('task_completed')}</p>
              <button
                onClick={handleShare}
                className="mt-2 bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all"
              >
                {t('share_with_friends')}
              </button>
            </>
          ) : (
            <p className="text-[#7ee9ff] text-xs">{t('keep_going')}</p>
          )}
        </div>
      )}
    </div>
  );
};

export default Tasks;















