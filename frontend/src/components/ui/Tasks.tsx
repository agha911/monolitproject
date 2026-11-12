import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from '../config';
import WebApp, { isDemo, showDemoNotice } from '../../telegram';

/** ======================= Types ======================= */
type Slide = { title: string; text: string; image?: string };
type PartnerTask = {
  id: string;
  partner_name: string;
  slides: Slide[];
  ig_username: string;
  ig_url: string;
  reward: number;
  claimed: boolean;
};

/** ======================= Modal (inline) ======================= */
const PartnerSlidesModal: React.FC<{
  onClose: () => void;
  task: PartnerTask;
  onClaimSuccess: () => void;
}> = ({ onClose, task, onClaimSuccess }) => {
  const { t } = useTranslation();
  const [i, setI] = useState(0);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const last = i >= task.slides.length - 1;
  const slide = task.slides[i];
  const initData = WebApp.initData || '';
  const igUrl = task.ig_url || `https://www.instagram.com/promo_express_az?igsh=MTdtZWFpbWNlMG9hcw==`;

  const next = () => setI((x) => Math.min(x + 1, task.slides.length - 1));

  const claim = async () => {
    if (isDemo) { showDemoNotice('Partner promotions are unavailable in this demo.'); return; }
    try {
      setBusy(true);
      window.open(igUrl, '_blank', 'noopener,noreferrer');
      const res = await fetch(`${API_BASE_URL}/api/partner/claim`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: initData }),
      });
      const data = await res.json();
      if (data.status === 'ok') {
        setMsg(t('slides_award_received', { amount: task.reward.toLocaleString() }));
        onClaimSuccess();
        setTimeout(onClose, 900);
      } else if (data.status === 'already_claimed') {
        setMsg(t('slides_already_claimed'));
        onClaimSuccess();
        setTimeout(onClose, 900);
      } else {
        setMsg(t('slides_error'));
      }
    } catch {
      setMsg(t('slides_network_error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center p-3">
      <div className="w-full max-w-sm rounded-2xl bg-[#0e1a2b] text-[#00f0ff] border border-[#00f0ff40] shadow-xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-3 border-b border-[#00f0ff20]">
          <div className="text-xs opacity-80">{i + 1}/{task.slides.length}</div>
          <button onClick={onClose} className="text-xs opacity-80 hover:opacity-100">{t('slides_close')}</button>
        </div>

        {/* Slide content */}
        <div className="p-3 text-center space-y-3">
          <h3 className="font-semibold">{slide.title}</h3>
          {slide.image && (
            <img
              src={slide.image}
              alt={slide.title}
              className="w-full max-h-64 object-contain rounded-xl border border-[#00f0ff20] bg-[#131f2f]"
              onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
            />
          )}
          <p className="text-sm opacity-80">{slide.text}</p>

          {/* Dots */}
          <div className="flex justify-center gap-1 mt-1">
            {task.slides.map((_, idx) => (
              <span
                key={idx}
                className={`w-2 h-2 rounded-full ${idx === i ? 'bg-[#00f0ff]' : 'bg-[#00f0ff33]'}`}
              />
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-[#00f0ff20]">
          {!last ? (
            <button
              className="w-full py-2 rounded-xl bg-[#00f0ff] text-[#0e1a2b]"
              onClick={next}
            >
              {t('slides_next')}
            </button>
          ) : (
            <button
              className="w-full py-2 rounded-xl bg-green-400 text-[#0e1a2b] disabled:opacity-60"
              onClick={claim}
              disabled={busy}
            >
              {busy ? t('slides_claiming') : t('slides_subscribe', { username: task.ig_username })}
            </button>
          )}
          {msg && <div className="text-center text-xs mt-2 opacity-90">{msg}</div>}
        </div>
      </div>
    </div>
  );
};

/** ======================= Page ======================= */
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
  const [, setReward] = useState<number | null>(null);
  const [checkedIn, setCheckedIn] = useState(false);
  const [checkinMessage, setCheckinMessage] = useState('');

  const [dailyTarget, setDailyTarget] = useState<number | null>(null);
  const [dailyProgress, setDailyProgress] = useState<number | null>(null);
  const [dailyCompleted, setDailyCompleted] = useState<boolean>(false);

  const [rewardMessage, setRewardMessage] = useState('');
  const [rewardClaimed, setRewardClaimed] = useState(false);

  // Partner task state
  const [partnerTask, setPartnerTask] = useState<PartnerTask | null>(null);
  const [partnerOpen, setPartnerOpen] = useState(false);
  const [partnerDone, setPartnerDone] = useState(false);

  const rewards = [10000, 20000, 30000, 40000, 50000, 60000, 70000];

  // ✅ Функция форматирования чисел
  const formatNumber = (num: number): string => {
    if (num >= 1000000) return `${num / 1000000}M`;
    if (num >= 1000) return `${num / 1000}k`;
    return num.toString();
  };

  /** ---------- Daily Task ---------- */
  const fetchDailyTask = useCallback(async () => {
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
  }, [telegramUserId]);

  useEffect(() => {
    fetchDailyTask();
  }, [fetchDailyTask]);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchDailyTask();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchDailyTask]);

  /** ---------- Partner Task: load on mount ---------- */
  useEffect(() => {
    if (isDemo) return;
    const loadPartnerTask = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/partner/task`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });
        const data: PartnerTask = await res.json();
        setPartnerTask(data);
        setPartnerDone(Boolean(data.claimed));
      } catch (e) {
        console.error('Partner task load error', e);
      }
    };
    loadPartnerTask();
  }, []);

  /** ---------- Old Instagram task (kept) ---------- */
  const handleInstagramClick = () => {
    if (isDemo) { showDemoNotice('Social subscription tasks require the real Telegram app.'); return; }
    window.open('https://www.instagram.com/gap_pick', '_blank');
    setOpenedInstagram(true);
  };

  const handleGroupClick = () => {
    if (isDemo) { showDemoNotice('Social subscription tasks require the real Telegram app.'); return; }
    window.open('https://t.me/+h-VjXbnz0BI2OGI6', '_blank');
    setOpenedGroup(true);
  };

  const handleComplete = async (task_id: string, setter: (done: boolean) => void, msgSetter: (message: string) => void) => {
    if (!telegramUserId) {
      msgSetter(t('error_user_unknown'));
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
    } catch {
      msgSetter(t('error'));
    }
  };

  const handleCheckIn = async () => {
    if (!telegramUserId) {
      setCheckinMessage(t('error_user_unknown'));
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
    } catch {
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
    } catch {
      setRewardMessage(t('error'));
    }
  };

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff] space-y-6">
      <h2 className="text-xl font-bold text-center drop-shadow-md">📋 {t('title_tasks')}</h2>

      {/* Partner task card */}
      {partnerTask && (
        <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow text-center flex items-center gap-3">
          <div className="flex-1 text-left">
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold text-[#7ee9ff]">{partnerTask.partner_name}</h3>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-200/20 text-emerald-300 border border-emerald-300/30">
                {t('partner_new')}
              </span>
            </div>
            <p className="text-xs text-[#a0f6ff] mt-1">
              {t('partner_card_subtitle')}
            </p>
            <div className="mt-2 flex items-center justify-between text-sm">
              <div className="opacity-90">
                {t('partner_reward_label')}: <span className="font-semibold">{partnerTask.reward.toLocaleString()} GAP</span>
              </div>
              <div>
                {partnerDone ? (
                  <span className="text-emerald-400 font-medium">{t('partner_done')}</span>
                ) : (
                  <span className="opacity-70">{t('partner_progress')}</span>
                )}
              </div>
            </div>
          </div>
          <button
            className="ml-2 px-4 py-2 rounded-xl bg-[#00f0ff] text-[#0e1a2b] disabled:opacity-50"
            onClick={() => setPartnerOpen(true)}
            disabled={partnerDone}
          >
            {t('partner_learn_more')}
          </button>
        </div>
      )}

      {/* Instagram (старое задание — оставлено как было) */}
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
              {formatNumber(r)}
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

      {/* Modal mount */}
      {partnerTask && partnerOpen && (
        <PartnerSlidesModal
          onClose={() => setPartnerOpen(false)}
          task={partnerTask}
          onClaimSuccess={() => setPartnerDone(true)}
        />
      )}
    </div>
  );
};

export default Tasks;























