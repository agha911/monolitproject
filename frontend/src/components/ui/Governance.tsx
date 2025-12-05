import React, { useEffect, useState, useMemo } from 'react';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from '../config';

const CURRENT_PROPOSAL_ID = 3; // fallback для завершённого голосования

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
  balance: number; // остаток DAO-баланса (remaining)
};

type DaoResultItem = {
  option_id: number;
  art_work_id: number | null;
  label: string | null;
  art_title: string | null;
  art_image_url: string | null;
  total_weight: number;
  votes_count: number;
};

type DaoResultsOut = {
  proposal_id: number;
  title: string;
  results: DaoResultItem[];
};

// ---------- картинка ----------
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

const DaoPage: React.FC = () => {
  const { t } = useTranslation('dao');

  const [telegramUser, setTelegramUser] = useState<any | null>(null);

  const [proposals, setProposals] = useState<DaoProposal[]>([]);
  const [loadingProposals, setLoadingProposals] = useState(true);

  // финальные результаты (когда голосование завершено)
  const [results, setResults] = useState<DaoResultsOut | null>(null);
  const [loadingResults, setLoadingResults] = useState(false);

  // лайв-результаты по активному голосованию
  const [liveResults, setLiveResults] = useState<DaoResultsOut | null>(null);
  const [loadingLiveResults, setLoadingLiveResults] = useState(false);

  // общий GAP (total_xp)
  const [balance, setBalance] = useState<number>(0);
  const [loadingBalance, setLoadingBalance] = useState(true);

  // DAO-баланс (остаток лимита по текущему голосованию)
  const [votingBalance, setVotingBalance] = useState<number>(0);

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

  // ================= ЗАГРУЗКА ОБЩЕГО БАЛАНСА (total_xp) =================
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
        const totalXp = Number(data.total_xp ?? 0);
        setBalance(totalXp);
      } catch (e) {
        console.error('Ошибка загрузки баланса:', e);
        setBalance(0);
      } finally {
        setLoadingBalance(false);
      }
    })();
  }, [initData]);

  // ================= ЗАГРУЗКА АКТИВНЫХ ГОЛОСОВАНИЙ / РЕЗУЛЬТАТОВ =================
  useEffect(() => {
    (async () => {
      try {
        setLoadingProposals(true);
        const res = await fetch(`${API_BASE_URL}/api/dao/proposals/active`);
        const data: DaoProposal[] = await res.json();
        setProposals(data || []);

        // если активных голосований нет — показываем финальные результаты по текущему ID
        if (!data || data.length === 0) {
          setLoadingResults(true);
          try {
            const r = await fetch(
              `${API_BASE_URL}/api/dao/proposals/${CURRENT_PROPOSAL_ID}/results`
            );
            if (r.ok) {
              const rs: DaoResultsOut = await r.json();
              setResults(rs);
            } else {
              console.warn('results HTTP error', r.status);
            }
          } catch (err) {
            console.error('Ошибка загрузки результатов:', err);
          } finally {
            setLoadingResults(false);
          }
        } else {
          // есть активное голосование — подгружаем лайв-результаты по нему
          const active = data[0];
          setLoadingLiveResults(true);
          try {
            const r = await fetch(
              `${API_BASE_URL}/api/dao/proposals/${active.id}/results`
            );
            if (r.ok) {
              const rs: DaoResultsOut = await r.json();
              setLiveResults(rs);
            } else {
              console.warn('live results HTTP error', r.status);
            }
          } catch (err) {
            console.error('Ошибка загрузки live-results:', err);
          } finally {
            setLoadingLiveResults(false);
          }
        }
      } catch (e) {
        console.error('Ошибка загрузки голосований:', e);
      } finally {
        setLoadingProposals(false);
      }
    })();
  }, []);

  const selectedProposal = proposals.length > 0 ? proposals[0] : null;

  // ================= ЗАГРУЗКА DAO-БАЛАНСА (остаток лимита) =================
  useEffect(() => {
    if (!initData || !selectedProposal) return;

    (async () => {
      try {
        const daoRes = await fetch(
          `${API_BASE_URL}/api/dao/proposals/${selectedProposal.id}/voting-balance`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ init_data: initData }),
          }
        );

        if (daoRes.ok) {
          const daoData = await daoRes.json();
          const eff = Number(daoData.balance ?? 0);
          setVotingBalance(eff >= 0 ? eff : 0);
        } else {
          console.warn('DAO voting-balance HTTP error:', daoRes.status);
          setVotingBalance(0);
        }
      } catch (err) {
        console.error('DAO voting-balance fetch failed:', err);
        setVotingBalance(0);
      }
    })();
  }, [initData, selectedProposal?.id]);

  const usedLocally = useMemo(
    () => Object.values(votes).reduce((s, w) => s + w, 0),
    [votes]
  );

  // effectiveBalance = DAO-баланс, а не total_xp
  const effectiveBalance = votingBalance;
  const remaining = Math.max(0, effectiveBalance - usedLocally);

  // ---------- лайв-результаты в виде map по option_id ----------
  const liveTotals = useMemo(() => {
    if (!liveResults) return {} as Record<
      number,
      { total: number; percent: number }
    >;

    const total = liveResults.results.reduce(
      (s, r) => s + (r.total_weight || 0),
      0
    );

    const map: Record<number, { total: number; percent: number }> = {};
    liveResults.results.forEach((r) => {
      const w = r.total_weight || 0;
      const pct = total ? Math.round((w / total) * 100) : 0;
      map[r.option_id] = { total: w, percent: pct };
    });

    return map;
  }, [liveResults]);

  // ---------- пресеты ----------
  const setVotePercent = (optionId: number, fraction: number) => {
    if (!selectedProposal) return;
    setError(null);
    setMessage(null);

    setVotes((prev) => {
      const target = Math.floor(effectiveBalance * fraction);
      const usedWithout = Object.entries(prev).reduce((s, [id, w]) => {
        return s + (Number(id) === optionId ? 0 : w);
      }, 0);

      const maxAllowed = Math.max(0, effectiveBalance - usedWithout);
      return { ...prev, [optionId]: Math.min(target, maxAllowed) };
    });
  };

  // ---------- отправка голосов ----------
  const handleSubmit = async () => {
    if (!selectedProposal) return;
    if (!initData) {
      setError(
        t('errors.init_data_missing', {
          defaultValue: 'Telegram WebApp başlanğıcı alınmadı',
        })
      );
      return;
    }

    const items: VoteItem[] = Object.entries(votes)
      .filter(([, w]) => w > 0)
      .map(([id, w]) => ({ option_id: Number(id), weight: w }));

    if (items.length === 0) {
      setError(
        t('errors.no_votes', {
          defaultValue: 'Siz səs ayırmamısınız',
        })
      );
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

      const data: VoteResponse | any = await res.json();

      if (!res.ok) {
        const detail = (data && data.detail) || 'unknown';
        setError(
          t('errors.server', {
            detail,
            defaultValue: 'Xəta: {{detail}}',
          })
        );
        return;
      }

      // ожидаем, что бек вернёт:
      // - used_weight: сколько GAP было поставлено В ЭТОМ запросе
      // - balance: ОСТАТОК DAO-лимита (remaining)
      if (typeof data.balance === 'number') {
        setVotingBalance(data.balance);
      } else {
        const fallbackBalance = Math.max(
          0,
          effectiveBalance - (Number(data.used_weight ?? 0) || 0)
        );
        setVotingBalance(fallbackBalance);
      }

      setVotes({});

      const used = Number(data.used_weight ?? 0);

      setMessage(
        t('message.votes_accepted', {
          amount: used.toLocaleString(),
          defaultValue: 'Səslər qəbul edildi: {{amount}} GAP',
        })
      );

      // после успешного голосования обновляем лайв-результаты
      try {
        const r = await fetch(
          `${API_BASE_URL}/api/dao/proposals/${selectedProposal.id}/results`
        );
        if (r.ok) {
          const rs: DaoResultsOut = await r.json();
          setLiveResults(rs);
        }
      } catch (err) {
        console.error('Ошибка обновления live-results после голосования:', err);
      }
    } catch (e) {
      setError(
        t('errors.vote_error', {
          defaultValue: 'Səsvermə zamanı xəta baş verdi',
        })
      );
    } finally {
      setSubmitting(false);
    }
  };

  // =======================================================================================
  //                                     UI
  // =======================================================================================

  return (
    <div className="min-h-screen bg-[#131f2f] text-[#00f0ff] px-4 py-6 flex flex-col items-center">
      <h1 className="text-2xl font-bold mb-2">
        {t('title', { defaultValue: 'DAO səsvermə' })}
      </h1>

      {/* ==================== РЕЖИМ РЕЗУЛЬТАТОВ (ГОЛОСОВАНИЕ ЗАВЕРШЕНО) ==================== */}
      {results && !selectedProposal && (
        <div className="w-full max-w-md bg-[#0e1a2b] border border-[#00f0ff40] rounded-2xl p-4 mt-4">
          <h2 className="text-lg font-semibold mb-3 text-[#7ee9ff]">
            {t('results.heading', { defaultValue: 'Nəticələr:' })}{' '}
            {results.title}
          </h2>

          <div className="space-y-4">
            {results.results.map((r) => {
              const img = resolveImageUrl(r.art_image_url);
              const total = results.results.reduce(
                (s, x) => s + x.total_weight,
                0
              );
              const percent = total
                ? Math.round((r.total_weight / total) * 100)
                : 0;

              return (
                <div
                  key={r.option_id}
                  className="bg-[#111f33] rounded-xl border border-[#1f3b57] p-3 flex gap-3"
                >
                  <div className="w-16 h-16 rounded-lg bg-[#0d273d] overflow-hidden flex items-center justify-center">
                    {img ? (
                      <img src={img} className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-xs text-[#7ee9ff]">
                        {t('no_image', { defaultValue: 'Şəkil yoxdur' })}
                      </span>
                    )}
                  </div>

                  <div className="flex-1">
                    <div className="text-white text-sm font-semibold">
                      {r.art_title || r.label}
                    </div>
                    <div className="text-[#7ee9ff] text-xs mt-1">
                      {r.total_weight.toLocaleString()} GAP ({percent}%)
                    </div>
                    <div className="text-[#7ee9ff80] text-[10px]">
                      {t('results.votes_count', {
                        defaultValue: 'Səslərin sayı:',
                      })}{' '}
                      {r.votes_count}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ==================== РЕЖИМ ГОЛОСОВАНИЯ (АКТИВНОЕ) ==================== */}
      {!loadingProposals && selectedProposal && (
        <div className="w-full max-w-md bg-[#0e1a2b] border border-[#00f0ff40] rounded-2xl p-4 mt-4">
          <h2 className="text-lg font-semibold text-[#7ee9ff]">
            {selectedProposal.title}
          </h2>

          {/* Балансы */}
          <div className="mt-2 text-xs text-[#a0f6ff] flex flex-col gap-1">
            <div>
              <span className="opacity-80">Cəmi GAP balansı:</span>{' '}
              <span className="font-semibold">
                {balance.toLocaleString()}
              </span>
            </div>
            <div>
              <span className="opacity-80">
                Səsvermə üçün mövcud:
              </span>{' '}
              <span className="font-semibold">
                {remaining.toLocaleString()}
              </span>
            </div>
          </div>

          <div className="mt-3 space-y-3">
            {selectedProposal.options.map((opt) => {
              const current = votes[opt.id] || 0;
              const imgSrc = resolveImageUrl(opt.art_image_url);
              const live = liveTotals[opt.id];

              return (
                <div
                  key={opt.id}
                  className="bg-[#111f33] rounded-xl border border-[#1f3b57] p-3 flex gap-3"
                >
                  <div className="w-16 h-16 rounded-lg bg-[#0d273d] overflow-hidden flex items-center justify-center">
                    {imgSrc ? (
                      <img
                        src={imgSrc}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <span className="text-xs text-[#7ee9ff]">
                        {t('no_image', { defaultValue: 'Şəkil yoxdur' })}
                      </span>
                    )}
                  </div>

                  <div className="flex-1 flex flex-col gap-2">
                    <div className="text-sm font-semibold text-white">
                      {opt.art_title || opt.label}
                    </div>

                    <div className="flex items-center justify-between text-xs text-[#a0f6ff]">
                      <span>
                        {t('vote_label', { defaultValue: 'Səs:' })}{' '}
                        <span className="font-semibold">
                          {current.toLocaleString()}
                        </span>
                      </span>
                    </div>

                    {/* Лайв-результаты по опции */}
                    {live && (
                      <div className="text-[#7ee9ff] text-[10px]">
                        {live.total.toLocaleString()} GAP ({live.percent}%)
                      </div>
                    )}

                    <div className="mt-1 flex flex-wrap gap-1 justify-end">
                      {[0, 0.1, 0.25, 0.5, 1].map((fraction) => (
                        <button
                          key={fraction}
                          onClick={() => setVotePercent(opt.id, fraction)}
                          disabled={submitting || effectiveBalance <= 0}
                          className="px-2 py-1 rounded-full bg-[#0d273d] border border-[#1f3b57] text-[10px] leading-none text-[#7ee9ff] min-w-[40px] text-center"
                        >
                          {Math.round(fraction * 100)}%
                        </button>
                      ))}
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
            {t('submit_button', { defaultValue: 'Səs vermək' })}
          </button>
        </div>
      )}

      {error && (
        <div className="mt-4 text-red-300 text-xs">
          {error}
        </div>
      )}
      {message && (
        <div className="mt-4 text-[#a0f6ff] text-xs">
          {message}
        </div>
      )}
    </div>
  );
};

export default DaoPage;
















