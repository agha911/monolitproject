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

  const [rewardMessage, setRewardMessage] = useState('');
  const [rewardClaimed, setRewardClaimed] = useState(false);

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
        setRewardClaimed(data.daily_reward_claimed);
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

  const handleClaimReward = async () => {
    if (!telegramUserId) return;

    try {
      const res = await fetch(`${API_BASE_URL}/api/daily/claim_reward`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: WebApp.initData }),
      });

      const data = await res.json();
      if (data.status === 'reward_claimed') {
        setRewardClaimed(true);
        setRewardMessage(`🎁 ${t('reward_received', { amount: data.reward })}`);
      } else if (data.status === 'already_claimed') {
        setRewardClaimed(true);
        setRewardMessage(`✅ ${t('already_claimed')}`);
      } else if (data.status === 'not_completed') {
        setRewardMessage(t('not_completed'));
      } else {
        setRewardMessage(t('error'));
      }
    } catch (err) {
      setRewardMessage(t('error'));
    }
  };

  const rewards = [10k, 20k, 30k, 40k, 50k, 60k, 70k];

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff] space-y-6">
      <h2 className="text-xl font-bold text-center drop-shadow-md">📋 {t('title_tasks')}</h2>

      {/* Instagram */}
      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow text-center">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">{t('subscribe_instagram')}</h3>
        <p className="text-sm text-[#a0f6ff]">{t('reward_received', { amount: 150000 })}</p>
        {!openedInstagram ? (
          <button onClick={handleInstagramClick} className="mt-2 bg-[#00f0ff] text-[#0e1a2b] px-4 py-2 rounded">{t('go_to_instagram')}</button>
        ) : (
          <button onClick={() => handleComplete('follow_instagram', setCompleted, setMessage)} disabled={completed}
            className="mt-2 bg-[#00f0ff] text-[#0e1a2b] px-4 py-2 rounded disabled:opacity-50">
            {completed ? t('already_done') : t('i_subscribed')}
          </button>
        )}
        {message && <p className="text-sm mt-2 text-[#a0f6ff]">{message}</p>}
      </div>

      {/* Telegram group */}
      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow text-center">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">{t('join_community')}</h3>
        <p className="text-sm text-[#a0f6ff]">{t('reward_received', { amount: 150000 })}</p>
        {!openedGroup ? (
          <button onClick={handleGroupClick} className="mt-2 bg-[#00f0ff] text-[#0e1a2b] px-4 py-2 rounded">{t('go_to_group')}</button>
        ) : (
          <button onClick={() => handleComplete('join_group', setJoined, setGroupMessage)} disabled={joined}
            className="mt-2 bg-[#00f0ff] text-[#0e1a2b] px-4 py-2 rounded disabled:opacity-50">
            {joined ? t('already_done') : t('i_joined')}
          </button>
        )}
        {groupMessage && <p className="text-sm mt-2 text-[#a0f6ff]">{groupMessage}</p>}
      </div>

      {/* Check-in */}
      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow text-center">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">{t('daily_checkin')}</h3>
        <p className="text-sm text-[#a0f6ff]">{t('checkin_get')}</p>
        <div className="flex justify-center gap-2 mt-2">
          {rewards.map((r, index) => (
            <div key={index} className={`w-8 h-8 flex items-center justify-center rounded-full text-xs font-bold ${streak && index < streak ? 'bg-[#00f0ff] text-[#0e1a2b]' : 'bg-[#1e2e3d] text-[#7ee9ff]'}`}>
              {r}
            </div>
          ))}
        </div>
        <button onClick={handleCheckIn} disabled={checkedIn}
          className="mt-4 bg-[#00f0ff] text-[#0e1a2b] px-4 py-2 rounded disabled:opacity-50">
          {checkedIn ? t('checkin_already') : t('checkin_get')}
        </button>
        {checkinMessage && <p className="text-sm mt-2 text-[#a0f6ff]">{checkinMessage}</p>}
      </div>

      {/* Daily click task */}
      {dailyTarget !== null && dailyProgress !== null && (
        <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow text-center">
          <h3 className="text-lg font-semibold text-[#7ee9ff]">{t('daily_task_clicker')}</h3>
          <div className="w-full h-4 bg-[#1e2e3d] rounded-full overflow-hidden">
            <div className="h-full bg-[#00f0ff]" style={{ width: `${Math.min((dailyProgress / dailyTarget) * 100, 100)}%` }}></div>
          </div>
          <p className="text-sm text-[#a0f6ff]">{t('daily_task_goal')}: {dailyProgress} / {dailyTarget}</p>
          {dailyCompleted ? (
            <>
              <p className="text-green-400 text-sm font-semibold">{t('task_completed')}</p>
              <button onClick={handleClaimReward} disabled={rewardClaimed} className="mt-2 bg-[#00f0ff] text-[#0e1a2b] px-4 py-2 rounded disabled:opacity-50">
                {rewardClaimed ? t('reward_received_short') : t('claim_reward')}
              </button>
              {rewardMessage && <p className="text-sm mt-2 text-[#a0f6ff]">{rewardMessage}</p>}
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





















