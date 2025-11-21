import React, { useEffect, useState, useMemo } from 'react';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from '../config';

type DaoOptionArt = {
  id: number;
  label: string | null;
  art_work_id: number | null;
  art_title: string | null;
  art_image_url: string | null;
  art_author_telegram_id: number | null;
};

type DaoProposal = {
  id: number;
  title: string;
  description: string;
  starts_at: string;
  ends_at: string;
  options: DaoOptionArt[];
};

type VoteItem = {
  option_id: number;
  weight: number;
};

type VoteResponse = {
  status: string;
  used_weight: number;
  balance: number;
};

// ----------- FIX №1: корректная обработка URL картинки -------------
const resolveImageUrl = (src: string | null): string | null => {
  if (!src) return null;

  // Если пришёл абсолютный URL — забираем только path, чтобы всегда грузить
  // картинку с ТЕКУЩЕГО домена фронта (origin), а не зашитого в БД.
  try {
    if (/^https?:\/\//i.test(src)) {
      const u = new URL(src);
      return u.pathname || null; // например: "/mascot-bw.png"
    }
  } catch {
    // если URL сломан — просто идём дальше и пытаемся работать как с относительным
  }

  // Относительный путь — гарантируем ведущий слэш
  if (!src.startsWith('/')) src = '/' + src;

  return src; // браузер сам подставит текущий origin
};
// ------------------------------------------------------------------

const DaoPage: React.FC = () => {
  const { t } = useTranslation();

  const [telegramUser, setTelegramUser] = useState<any | null>(null);

  const [proposals, setProposals] = useState<DaoProposal[]>([]);
  const [loadingProposals, setLoadingProposals] = useState(true);

  const [balance, setBalance] = useState<number>(0);
  const [loadingBalance, setLoadingBalance] = useState(true);

  const [votes, setVotes] = useState<Record<number, number>>({});
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Telegram init
  useEffect(() => {
    WebApp.ready();
    const user = WebApp.initDataUnsafe?.user;
    if (user) setTelegramUser(user);
  }, []);

  const initData = WebApp.initData;

  // загрузка баланса
  useEffect(() => {
    if (!initData) return;

    (async () => {
      try {
        setLoadingBalance(true);
        const res = await fetch(`${API_BASE_URL}/api/game/progress`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: initData }),
        });
        const data = await res.json();
        setBalance(Number(data.total_xp ?? 0));
      } catch (e) {
        console.error('Ошибка загрузки баланса для DAO:', e);
      } finally {
        setLoadingBalance(false);
      }
    })();
  }, [initData]);

  // загрузка активных предложений
  useEffect(() => {
    (async () => {
      try {
        setLoadingProposals(true);
        const res = await fetch(`${API_BASE_URL}/api/dao/proposals/active`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data: DaoProposal[] = await res.json();
        setProposals(data || []);
      } catch (e) {
        console.error('Ошибка загрузки DAO-предложений:', e);
      } finally {
        setLoadingProposals(false);
      }
    })();
  }, []);

  const selectedProposal = useMemo(
    () => (proposals.length > 0 ? proposals[0] : null),
    [proposals]
  );

  const usedLocally = useMemo(
    () => Object.values(votes).reduce((s, w) => s + w, 0),
    [votes]
  );
  const remaining = Math.max(0, balance - usedLocally);

  // ----------- FIX №2: пресеты включая 0% ------------------
  const setVotePercent = (optionId: number, fraction: number) => {
    if (!selectedProposal) return;
    setError(null);
    setMessage(null);

    setVotes((prev) => {
      const target = Math.floor(balance * fraction);

      // вычисляем остаток для нормального распределения
      const usedWithoutThis = Object.entries(prev).reduce((sum, [id, w]) => {
        return sum + (Number(id) === optionId ? 0 : w);
      }, 0);

      const maxForThisOption = Math.max(0, balance - usedWithoutThis);
      const next = Math.min(target, maxForThisOption);

      return { ...prev, [optionId]: next };
    });
  };
  // ---------------------------------------------------------

  const handleSubmit = async () => {
    if (!selectedProposal) return;
    if (!initData) {
      setError('init_data_missing');
      return;
    }

    const items: VoteItem[] = Object.entries(votes)
      .filter(([, w]) => w > 0)
      .map(([id, w]) => ({ option_id: Number(id), weight: w }));

    if (items.length === 0) {
      setError(t('dao.no_votes_selected', { defaultValue: 'Вы не распределили голоса' }));
      return;
    }

    setSubmitting(true);
    setError(null);
    setMessage(null);

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/dao/proposals/${selectedProposal.id}/vote`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: initData, votes: items }),
        }
      );

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail = data?.detail || `HTTP ${res.status}`;
        setError(
          t('dao.vote_error', {
            defaultValue: 'Ошибка при отправке голоса: {{detail}}',
            detail: String(detail),
          })
        );
        return;
      }

      const data: VoteResponse = await res.json();
      if (data.status === 'ok') {
        setMessage(
          t('dao.vote_success', {
            defaultValue: 'Голоса учтены. Использовано {{used}} из {{balance}} $GAP.',
            used: data.used_weight,
            balance: data.balance,
          })
        );
        setBalance(data.balance);
        setVotes({});
      } else {
        setError(t('dao.vote_error_status', { defaultValue: 'Ошибка: {{status}}', status: data.status }));
      }
    } catch (e: any) {
      console.error('DAO vote error:', e);
      setError(
        t('dao.vote_error', {
          defaultValue: 'Ошибка при отправке голоса: {{detail}}',
          detail: e?.message || 'unknown',
        })
      );
    } finally {
      setSubmitting(false);
    }
  };

  // UI
  return (
    <div className="min-h-screen bg-[#131f2f] text-[#00f0ff] px-4 py-6 flex flex-col items-center">
      <h1 className="text-2xl font-bold mb-2 text-center drop-shadow-md">
        {t('dao.title', { defaultValue: 'DAO səsvermə' })}
      </h1>

      <p className="text-sm text-[#7ee9ff] mb-4 text-center max-w-md">
        {t('dao.subtitle', {
          defaultValue: 'Gappick DAO: Səsin çəkisi — sənin $GAP balansındır.',
        })}
      </p>

      <div className="w-full max-w-md bg-[#0e1a2b] border border-[#00f0ff40] rounded-xl p-3 mb-4">
        <div className="text-xs text-[#7ee9ff] mb-1">
          {t('dao.balance_label', { defaultValue: 'Sənin balansın' })}
        </div>
        <div className="flex items-baseline justify-between">
          <div className="text-lg font-semibold">
            {loadingBalance ? '…' : `${balance.toLocaleString()} $GAP`}
          </div>
          <div className="text-xs text-[#a0f6ff]">
            {t('dao.remaining', {
              defaultValue: 'Bu səsvermə üçün qalan: {{value}}',
              value: remaining.toLocaleString(),
            })}{' '}
            $GAP
          </div>
        </div>
      </div>

      {!loadingProposals && selectedProposal && (
        <div className="w-full max-w-md bg-[#0e1a2b] border border-[#00f0ff40] rounded-2xl p-4 mt-2">
          <h2 className="text-lg font-semibold text-[#7ee9ff]">
            {selectedProposal.title}
          </h2>

          <div className="mt-3 space-y-3">
            {selectedProposal.options.map((opt) => {
              const current = votes[opt.id] || 0;
              const imgSrc = resolveImageUrl(opt.art_image_url);

              return (
                <div key={opt.id} className="bg-[#111f33] border border-[#1f3b57] rounded-xl p-3 flex gap-3">
                  <div className="w-16 h-16 rounded-lg overflow-hidden flex-shrink-0 bg-[#0d273d] flex items-center justify-center">
                    {imgSrc ? (
                      <img src={imgSrc} className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-xs text-[#7ee9ff] text-center">No image</span>
                    )}
                  </div>

                  <div className="flex-1 flex flex-col justify-between">
                    <div className="text-sm font-semibold text-white">
                      {opt.art_title || opt.label}
                    </div>

                    <div className="mt-2 flex items-center justify-between gap-2">
                      <div className="text-xs text-[#a0f6ff]">
                        Səs: <span className="font-semibold">{current.toLocaleString()}</span>
                      </div>

                      {/* ---- FIX №3: пресеты 0 / 10 / 25 / 50 / 100 ---- */}
                      <div className="flex gap-1">
                        {[0, 0.1, 0.25, 0.5, 1].map((fraction) => (
                          <button
                            key={fraction}
                            onClick={() => setVotePercent(opt.id, fraction)}
                            disabled={submitting || balance <= 0}
                            className="px-2 py-1 rounded-full bg-[#0d273d] border border-[#1f3b57] text-[10px] text-[#7ee9ff] active:scale-95"
                          >
                            {Math.round(fraction * 100)}%
                          </button>
                        ))}
                      </div>
                      {/* ------------------------------------------------ */}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <button
            className="mt-4 w-full py-2.5 rounded-xl bg-[#00f0ff] text-[#0e1a2b] font-semibold"
            disabled={submitting || usedLocally <= 0}
            onClick={handleSubmit}
          >
            Səs vermək
          </button>
        </div>
      )}

      {error && <div className="mt-4 text-red-300 text-xs">{error}</div>}
      {message && <div className="mt-4 text-[#a0f6ff] text-xs">{message}</div>}
    </div>
  );
};

export default DaoPage;







