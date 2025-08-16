import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from '../config';
import WebApp from '@twa-dev/sdk';

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
  const [i, setI] = useState(0);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const last = i >= task.slides.length - 1;
  const slide = task.slides[i];
  const initData = WebApp.initData || '';
  const igUrl = task.ig_url || `https://instagram.com/${task.ig_username}`;

  const next = () => setI((x) => Math.min(x + 1, task.slides.length - 1));

  const claim = async () => {
    try {
      setBusy(true);
      window.open(igUrl, '_blank', 'noopener,noreferrer');
      const res = await fetch(`${API_BASE_URL}/api/partner/claim`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: initData }),
      });
      const data = await res.json();
      if (data.status === 'ok' || data.status === 'already_claimed') {
        setMsg(data.status === 'ok' ? `+${task.reward.toLocaleString()} GAP` : 'Artıq qəbul olunub');
        onClaimSuccess();
        setTimeout(onClose, 900);
      } else {
        setMsg('Xəta baş verdi');
      }
    } catch {
      setMsg('Şəbəkə xətası');
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
          <button onClick={onClose} className="text-xs opacity-80 hover:opacity-100">Bağla</button>
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
              Daha
            </button>
          ) : (
            <button
              className="w-full py-2 rounded-xl bg-green-400 text-[#0e1a2b] disabled:opacity-60"
              onClick={claim}
              disabled={busy}
            >
              {busy ? 'Gözləyin...' : `Abunə ol (@${task.ig_username})`}
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
  const [reward, setReward] = useState<number | null>(null);
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

  /** ---------- Partner Task: load on mount ---------- */
  useEffect(() => {
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

  /** ---------- Old Instagram task (keep as-is) ---------- */
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

      const da























