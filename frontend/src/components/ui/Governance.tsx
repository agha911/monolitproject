import React, { useEffect, useState, useMemo } from 'react';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from '../config';

type DaoOption = {
  id: number;
  label: string;
  description?: string | null;
  art_image_url?: string | null;
  total_votes: number;
};

type DaoProposal = {
  id: number;
  title: string;
  description?: string | null;
  status: 'draft' | 'active' | 'finished';
  total_votes: number;
  options: DaoOption[];
};

type ActiveProposalResponse = {
  proposal: DaoProposal | null;
  user_balance: number;
  user_votes_used: number;
};

const Governance: React.FC = () => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [proposal, setProposal] = useState<DaoProposal | null>(null);
  const [userBalance, setUserBalance] = useState(0);         // сколько GAP у юзера всего
  const [userVotesUsed, setUserVotesUsed] = useState(0);     // сколько голосов уже отдал в этом голосовании
  const [selectedVotes, setSelectedVotes] = useState<Record<number, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const remainingVotes = useMemo(() => {
    const allocated = Object.values(selectedVotes).reduce((sum, v) => sum + (v || 0), 0);
    const free = Math.max(0, userBalance - userVotesUsed);
    return Math.max(0, free - allocated);
  }, [selectedVotes, userBalance, userVotesUsed]);

  // загружаем активное голосование
  useEffect(() => {
    WebApp.ready();
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch(`${API_BASE_URL}/api/dao/proposals/active`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });
        if (!res.ok) {
          throw new Error(`status: ${res.status}`);
        }
        const data: ActiveProposalResponse = await res.json();
        if (!data.proposal) {
          setProposal(null);
        } else {
          setProposal(data.proposal);
        }
        setUserBalance(data.user_balance || 0);
        setUserVotesUsed(data.user_votes_used || 0);
        setSelectedVotes({});
      } catch (e: any) {
        console.error('DAO load error', e);
        setError(t('dao.load_error', { defaultValue: 'Səsverməni yükləmək mümkün olmadı.' }));
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [t]);

  const freeVotes = useMemo(() => {
    const alreadyAllocated = userVotesUsed;
    const total = userBalance;
    return Math.max(0, total - alreadyAllocated);
  }, [userBalance, userVotesUsed]);

  const handlePreset = (optionId: number, percent: number) => {
    if (!proposal) return;
    // 0% — просто сбрасываем значение
    if (percent === 0) {
      setSelectedVotes((prev) => ({
        ...prev,
        [optionId]: 0,
      }));
      return;
    }
    const votesFromFree = Math.floor((freeVotes * percent) / 100);
    setSelectedVotes((prev) => ({
      ...prev,
      [optionId]: votesFromFree,
    }));
  };

  const handleSubmit = async () => {
    if (!proposal) return;
    const allocated = Object.values(selectedVotes).reduce((sum, v) => sum + (v || 0), 0);
    if (allocated <= 0) {
      setError(t('dao.no_votes_selected', { defaultValue: 'Heç bir səs seçilməyib.' }));
      return;
    }
    if (allocated > freeVotes) {
      setError(t('dao.too_many_votes', { defaultValue: 'Ayrılmış səslər mövcud saydan çoxdur.' }));
      return;
    }

    try {
      setSubmitting(true);
      setError(null);
      setSuccess(null);

      const payload = {
        init_data: WebApp.initData,
        proposal_id: proposal.id,
        votes: Object.entries(selectedVotes)
          .filter(([, v]) => (v || 0) > 0)
          .map(([optionId, v]) => ({
            option_id: Number(optionId),
            votes: Number(v),
          })),
      };

      const res = await fetch(`${API_BASE_URL}/api/dao/proposals/vote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        const detail = (errData && (errData.detail || errData.message)) || 'unknown';
        if (detail === 'proposal_closed') {
          setError(
            t('dao.proposal_closed', {
              defaultValue: 'Bu səsvermə artıq bağlanıb.',
            }),
          );
        } else if (detail === 'not_enough_balance') {
          setError(
            t('dao.not_enough_balance', {
              defaultValue: 'Bu qədər səs vermək üçün balansınız kifayət etmir.',
            }),
          );
        } else {
          setError(
            t('dao.vote_error_generic', {
              defaultValue: 'Səs vermə zamanı xəta baş verdi.',
            }) + ` (${detail})`,
          );
        }
        return;
      }

      const data = await res.json();
      setSuccess(
        t('dao.vote_success', {
          defaultValue: 'Səs(ler)iniz qeyd edildi, təşəkkür edirik!',
        }),
      );

      if (typeof data.user_balance === 'number') setUserBalance(data.user_balance);
      if (typeof data.user_votes_used === 'number') setUserVotesUsed(data.user_votes_used);
      setSelectedVotes({});
    } catch (e) {
      console.error('vote error', e);
      setError(
        t('dao.vote_error_generic', {
          defaultValue: 'Səs vermə zamanı xəta baş verdi.',
        }),
      );
    } finally {
      setSubmitting(false);
    }
  };

  // просто используем art_image_url как есть
  const getOptionImageUrl = (opt: DaoOption) => {
    const url = opt.art_image_url;
    if (!url) return null;
    return url; // в БД уже полный https://.../mascot-bw.png
  };

  if (loading) {
    return (
      <div className="w-full min-h-screen flex items-center justify-center bg-[#030712] text-white">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-2 border-t-transparent border-cyan-400 mx-auto mb-3" />
          <div className="text-sm text-gray-300">Yüklənir...</div>
        </div>
      </div>
    );
  }

  if (!proposal) {
    return (
      <div className="w-full min-h-screen flex items-center justify-center bg-[#030712] text-white px-4">
        <div className="max-w-md w-full text-center">
          <h1 className="text-xl font-semibold mb-2">DAO səsvermələri</h1>
          <p className="text-sm text-gray-300">
            Hal-hazırda aktiv səsvermə yoxdur. Tezliklə yeni qərarlar və seçimlər əlavə olunacaq.
          </p>
        </div>
      </div>
    );
  }

  const allocatedNow = Object.values(selectedVotes).reduce(
    (sum, v) => sum + (v || 0),
    0,
  );
  const freeVotesNow = Math.max(0, freeVotes - allocatedNow);

  return (
    <div className="w-full min-h-screen bg-[#030712] text-white px-4 pt-6 pb-10">
      <div className="max-w-xl mx-auto">
        <h1 className="text-2xl font-bold mb-1">{t('dao.title', { defaultValue: 'DAO Səsvermə' })}</h1>
        <p className="text-xs text-gray-400 mb-4">
          {t('dao.subtitle', {
            defaultValue:
              'Sənin səsin — sənin GAP balansındır. Balansın qədər səs verə bilərsən.',
          })}
        </p>

        <div className="mb-4 p-3 rounded-xl bg-[#020617] border border-[#1f2937] flex items-center justify-between">
          <div>
            <div className="text-[11px] text-gray-400 uppercase tracking-wide mb-1">
              {t('dao.your_balance', { defaultValue: 'Sənin balansın' })}
            </div>
            <div className="text-lg font-semibold text-cyan-300">
              {userBalance.toLocaleString('ru-RU')} GAP
            </div>
          </div>
          <div className="text-right">
            <div className="text-[11px] text-gray-400 uppercase tracking-wide mb-1">
              {t('dao.votes_used', { defaultValue: 'Artıq istifadə olunan səs' })}
            </div>
            <div className="text-sm font-medium text-amber-300">
              {userVotesUsed.toLocaleString('ru-RU')}
            </div>
            <div className="text-[11px] text-gray-400 mt-1">
              {t('dao.votes_free', { defaultValue: 'Qalan səs:' })}{' '}
              <span className="text-cyan-300">
                {freeVotesNow.toLocaleString('ru-RU')}
              </span>
            </div>
          </div>
        </div>

        <div className="mb-4 p-4 rounded-2xl bg-gradient-to-br from-[#020617] via-[#020617] to-[#020617] border border-[#1f2937] shadow-lg shadow-cyan-900/20">
          <h2 className="text-lg font-semibold mb-1">{proposal.title}</h2>
          {proposal.description && (
            <p className="text-sm text-gray-300 mb-2 whitespace-pre-wrap">
              {proposal.description}
            </p>
          )}
          <p className="text-[11px] text-gray-400 mt-1">
            {t('dao.info_weight', {
              defaultValue:
                'Sənin səsvermə gücün GAP balansına bərabərdir. Eyni anda bir neçə seçimə səs verə bilərsən.',
            })}
          </p>
        </div>

        {error && (
          <div className="mb-3 p-3 rounded-xl bg-red-900/40 border border-red-500/60 text-sm text-red-100">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-3 p-3 rounded-xl bg-emerald-900/40 border border-emerald-500/60 text-sm text-emerald-100">
            {success}
          </div>
        )}

        <div className="space-y-4">
          {proposal.options.map((opt) => {
            const current = selectedVotes[opt.id] || 0;
            const imageUrl = getOptionImageUrl(opt);
            return (
              <div
                key={opt.id}
                className="p-3 rounded-2xl bg-[#020617] border border-[#1f2937] shadow-md shadow-cyan-900/10"
              >
                {imageUrl && (
                  <div className="w-full mb-2 rounded-xl overflow-hidden bg-black/40">
                    <img
                      src={imageUrl}
                      alt={opt.label}
                      className="w-full h-40 object-contain bg-black"
                      referrerPolicy="no-referrer"
                    />
                  </div>
                )}

                <div className="flex items-center justify-between mb-1">
                  <div>
                    <div className="text-sm font-semibold">{opt.label}</div>
                    {opt.description && (
                      <div className="text-xs text-gray-400 mt-0.5">
                        {opt.description}
                      </div>
                    )}
                  </div>
                  <div className="text-right">
                    <div className="text-[11px] text-gray-400">
                      {t('dao.option_total_votes', {
                        defaultValue: 'Toplam səslər:',
                      })}{' '}
                      <span className="text-cyan-300">
                        {opt.total_votes.toLocaleString('ru-RU')}
                      </span>
                    </div>
                    <div className="text-[11px] text-gray-400">
                      {t('dao.option_you_set', {
                        defaultValue: 'Sənin seçimin:',
                      })}{' '}
                      <span className="text-amber-300">
                        {current.toLocaleString('ru-RU')} GAP
                      </span>
                    </div>
                  </div>
                </div>

                {/* пресеты процентов, включая 0% (сброс) */}
                <div className="flex flex-wrap gap-2 mt-2">
                  {[0, 10, 25, 50, 100].map((pct) => (
                    <button
                      key={pct}
                      type="button"
                      className={`px-2.5 py-1 rounded-full text-[11px] border transition
                        ${
                          pct === 0
                            ? 'border-gray-600 text-gray-300 hover:bg-gray-700/40'
                            : 'border-cyan-500/60 text-cyan-200 hover:bg-cyan-500/10'
                        }
                      `}
                      onClick={() => handlePreset(opt.id, pct)}
                    >
                      {pct}%
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-5">
          <button
            type="button"
            disabled={submitting || Object.values(selectedVotes).every((v) => !v)}
            onClick={handleSubmit}
            className={`w-full py-2.5 rounded-2xl text-sm font-semibold shadow-lg
              ${
                submitting || Object.values(selectedVotes).every((v) => !v)
                  ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
                  : 'bg-cyan-500 text-black hover:bg-cyan-400'
              }`}
          >
            {submitting
              ? t('dao.button_voting_in_progress', {
                  defaultValue: 'Səs verilir...',
                })
              : t('dao.button_vote', {
                  defaultValue: 'Səs vermək',
                })}
          </button>
          <p className="mt-2 text-[11px] text-gray-500 text-center">
            {t('dao.disclaimer', {
              defaultValue:
                'Səsvermə test rejimindədir. GAP balansı yalnız oyun daxilində hesablanır.',
            })}
          </p>
        </div>
      </div>
    </div>
  );
};

export default DaoPage;







