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

// ==========================================================
//              Корректная загрузка картинки
// ==========================================================
const resolveImageUrl = (src: string | null): string | null => {
  if (!src) return null;
  try {
    if (/^https?:\/\//i.test(src)) {
      const u = new URL(src);
      return u.pathname || null;
    }
  } catch {}
  if (!src.startsWith('/')) src = '/' + src;
  return src;
};
// ==========================================================

const DaoPage: React.FC = () => {
  const { t } = useTranslation();

  const [telegramUser, setTelegramUser] = useState<any | null>(null);

  const [proposals, setProposals] = useState<DaoProposal[]>([]);
  const [loadingProposals, setLoadingProposals] = useState(true);

  // 🔹 votingBalance — лимит голосов для ЭТОГО голосования
  const [votingBalance, setVotingBalance] = useState<number>(0);
  const [loadingBalance, setLoadingBalance] = useState(true);

  // 🔹 сколько уже потрачено по этому proposal (по данным бэка)
  const [usedAlready, setUsedAlready] = useState<number>(0);

  // 🔹 флаг: уже был успешный голос → дальше /game/progress не трогает лимит
  const [hasVoted, setHasVoted] = useState<boolean>(false);

  const [votes, setVotes] = useState<Record<number, number>>({});
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    WebApp.ready();
    const user = WebApp.initDataUnsafe?.user;
    if (user) setTelegramUser(user);
  }, []);

  const initData = WebApp.initData;

  // --- загрузка исходного баланса (до первого голосования он же лимит) ---
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
        // Пока пользователь ещё не голосовал — берём лимит из total_xp.
        if (!hasVoted) {
          setVotingBalance(Number(data.total_xp ?? 0));
        }
      } catch (e) {
        console.error('Ошибка загрузки баланса:', e);
      } finally {
        setLoadingBalance(false);
      }
    })();
  }, [initData, hasVoted]);

  // --- загрузка предложений ---
  useEffect(() => {
    (async () => {
      try {
        setLoadingProposals(true);
        const res = await fetch(`${API_BASE_URL}/api/dao/proposals/active`);
        const data: DaoProposal[] = await res.json();
        setProposals(data || []);
      } catch (e) {
        console.error('Ошибка DAO:', e);
      } finally {
        setLoadingProposals(false);
      }
    })();
  }, []);

  const selectedProposal = useMemo(
    () => (proposals.length > 0 ? proposals[0] : null),
    [proposals]
  );

  // Локально выбранные веса в текущей сессии (ещё не отправлены)
  const usedLocally = useMemo(
    () => Object.values(votes).reduce((s, w) => s + w, 0),
    [votes]
  );

  // Реально доступно сейчас: лимит - уже потрачено - то, что пользователь сейчас раскидывает
  const remaining = Math.max(0, votingBalance - usedAlready - usedLocally);

  // ==========================================================
  //          Пресеты с учётом уже потраченного usedAlready
  // ==========================================================
  const setVotePercent = (optionId: number, fraction: number) => {
    if (!selectedProposal) return;
    setError(null);
    setMessage(null);

    setVotes((prev) => {
      const base = Math.max(0, votingBalance - usedAlready); // сколько вообще можно ещё раскидать
      const target = Math.floor(base * fraction);

      const usedWithoutThis = Object.entries(prev).reduce((sum, [id, w]) => {
        return sum + (Number(id) === optionId ? 0 : w);
      }, 0);

      const maxForThisOption = Math.max(0, base - usedWithoutThis);
      const next = Math.min(target, maxForThisOption);

      return { ...prev, [optionId]: next };
    });
  };
  // ==========================================================

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
      setError('Вы не распределили голоса');
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

      const data: VoteResponse & { detail?: string } = await res.json();

      if (res.ok && data.status === 'ok') {
        // ✅ фиксируем, что пользователь уже голосовал
        setHasVoted(true);

        // ✅ используем used_weight с бэка — сколько всего по этому proposal потрачено
        if (typeof data.used_weight === 'number') {
          setUsedAlready(Number(data.used_weight));
        }

        // ✅ balance — это уже серверный "зафиксированный" лимит для этого голосования
        if (typeof data.balance === 'number') {
          setVotingBalance(Number(data.balance));
        }

        setMessage(
          `Голоса учтены. Использовано ${data.used_weight.toLocaleString()} из ${data.balance.toLocaleString()} $GAP.`
        );
        setVotes({});
      } else {
        const statusText = data.status || data.detail || `HTTP ${res.status}`;
        setError(`Ошибка при отправке голоса: ${statusText}`);
      }
    } catch (e: any) {
      setError(`Ошибка: ${e?.message || 'unknown'}`);
    } finally {
      setSubmitting(false);
    }
  };

  // ==========================================================
  //                       UI
  // ==========================================================

  return (
    <div className="min-h-screen bg-[#131f2f] text-[#00f0ff] px-4 py-6 flex flex-col items-center">
      <h1 className="text-2xl font-bold mb-2 text-center">
        {t('dao.title', { defaultValue: 'DAO səsvermə' })}
      </h1>

      <p className="text-sm text-[#7ee9ff] mb-4 text-center max-w-md">
        Səsin çəkisi — sənin GAP balansındır. Bu səsvermə üçün limit bir dəfə sabitlənir.
      </p>

      {/* Блок лимита голосов для ЭТОГО голосования */}
      <div className="w-full max-w-md bg-[#0e1a2b] border border-[#00f0ff40] rounded-xl p-3 mb-4">
        <div className="text-xs mb-1 text-[#7ee9ff]">
          Bu səsvermə üçün GAP limiti
        </div>
        <div className="flex justify-between items-baseline">
          <div className="text-lg font-semibold">
            {loadingBalance ? '…' : `${votingBalance.toLocaleString()} $GAP`}
          </div>
          <div className="text-xs text-[#a0f6ff] text-right">
            Artıq istifadə olunub: {usedAlready.toLocaleString()} $GAP
            <br />
            Qalan: {remaining.toLocaleString()} $GAP
          </div>
        </div>
      </div>

      {/* Основной блок */}
      {!loadingProposals && selectedProposal && (
        <div className="w-full max-w-md bg-[#0e1a2b] border border-[#00f0ff40] rounded-2xl p-4 mt-2">
          <h2 className="text-lg font-semibold text-[#7ee9ff]">
            {selectedProposal.title}
          </h2>

          <div className="mt-3 space-y-4">
            {selectedProposal.options.map((opt) => {
              const current = votes[opt.id] || 0;
              const imgSrc = resolveImageUrl(opt.art_image_url);

              return (
                <div
                  key={opt.id}
                  className="bg-[#111f33] border border-[#1f3b57] rounded-xl p-4 flex gap-4"
                >
                  {/* картинка чуть крупнее */}
                  <div className="w-20 h-20 rounded-lg overflow-hidden flex-shrink-0 bg-[#0d273d] flex items-center justify-center">
                    {imgSrc ? (
                      <img src={imgSrc} className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-xs text-[#7ee9ff]">No image</span>
                    )}
                  </div>

                  <div className="flex-1 flex flex-col justify-between">
                    <div className="text-sm font-semibold text-white">
                      {opt.art_title || opt.label}
                    </div>

                    <div className="mt-3 flex items-center justify-between gap-2">
                      <div className="text-xs text-[#a0f6ff]">
                        Səs:{' '}
                        <span className="font-semibold">
                          {current.toLocaleString()}
                        </span>
                      </div>

                      {/* пресеты 0 / 10 / 25 / 50 / 100 */}
                      <div className="flex gap-1 flex-wrap">
                        {[0, 0.1, 0.25, 0.5, 1].map((fraction) => (
                          <button
                            key={fraction}
                            onClick={() => setVotePercent(opt.id, fraction)}
                            disabled={submitting || votingBalance - usedAlready <= 0}
                            className="px-2 py-1 rounded-full bg-[#0d273d] border border-[#1f3b57] text-[10px] text-[#7ee9ff] active:scale-95"
                          >
                            {Math.round(fraction * 100)}%
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <button
            className="mt-5 w-full py-3 rounded-xl bg-[#00f0ff] text-[#0e1a2b] font-semibold"
            disabled={submitting || usedLocally <= 0 || votingBalance - usedAlready <= 0}
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









