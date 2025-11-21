import React, { useEffect, useState } from 'react';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from '../config';

type DaoOption = {
  id: number;
  title: string;
  description?: string | null;
  image_url?: string | null;
  total_votes: number;
};

type DaoProposal = {
  id: number;
  title: string;
  description: string;
  status: string;
  starts_at: string;
  ends_at: string;
  options: DaoOption[];
};

type ActiveProposalsResponse = {
  proposals: DaoProposal[];
  user_balance: number; // сколько голосов (монет) доступно пользователю
};

type VotePayload = {
  proposal_id: number;
  votes: { option_id: number; amount: number }[];
};

const Governance: React.FC = () => {
  const { t } = useTranslation();
  const [proposals, setProposals] = useState<DaoProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // доступные «голоса» = баланс монет пользователя
  const [votesAvailable, setVotesAvailable] = useState<number>(0);

  // локальный ввод голосов: proposalId -> optionId -> amount
  const [localVotes, setLocalVotes] = useState<Record<number, Record<number, number>>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await fetch(`${API_BASE_URL}/api/dao/proposals/active`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }

        const data: ActiveProposalsResponse = await res.json();
        setProposals(data.proposals || []);
        setVotesAvailable(data.user_balance || 0);
        setError(null);
      } catch (e: any) {
        console.error('DAO fetch error', e);
        setError('Xəta baş verdi, bir az sonra yenidən yoxlayın.');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const getProposalVotes = (proposalId: number) => {
    const map = localVotes[proposalId] || {};
    return Object.values(map).reduce((sum, v) => sum + (v || 0), 0);
  };

  const changeVote = (proposalId: number, optionId: number, delta: number) => {
    if (delta === 0) return;
    setLocalVotes((prev) => {
      const current = { ...(prev[proposalId] || {}) };
      const currentForOption = current[optionId] || 0;

      const proposal = proposals.find((p) => p.id === proposalId);
      if (!proposal) return prev;

      const beforeTotal = Object.entries(current).reduce(
        (sum, [optId, val]) => sum + (Number(optId) === optionId ? 0 : (val || 0)),
        0
      );

      let newVal = currentForOption + delta;
      if (newVal < 0) newVal = 0;

      const afterTotal = beforeTotal + newVal;
      if (afterTotal > votesAvailable) {
        return prev;
      }

      if (newVal === 0) {
        delete current[optionId];
      } else {
        current[optionId] = newVal;
      }

      return { ...prev, [proposalId]: current };
    });
  };

  // пресеты: 0% (сброс), 10%, 25%, 50%, 100%
  const PRESETS = [0, 10, 25, 50, 100];

  const applyPreset = (proposalId: number, percent: number) => {
    const proposal = proposals.find((p) => p.id === proposalId);
    if (!proposal) return;

    if (percent === 0) {
      setLocalVotes((prev) => {
        const copy = { ...prev };
        copy[proposalId] = {};
        return copy;
      });
      return;
    }

    if (votesAvailable <= 0) return;

    const totalForPreset = Math.floor((votesAvailable * percent) / 100);
    if (totalForPreset <= 0) {
      setLocalVotes((prev) => {
        const copy = { ...prev };
        copy[proposalId] = {};
        return copy;
      });
      return;
    }

    const n = proposal.options.length;
    if (n === 0) return;

    const base = Math.floor(totalForPreset / n);
    let remainder = totalForPreset - base * n;

    const newVotes: Record<number, number> = {};
    for (const opt of proposal.options) {
      let v = base;
      if (remainder > 0) {
        v += 1;
        remainder -= 1;
      }
      newVotes[opt.id] = v;
    }

    setLocalVotes((prev) => ({
      ...prev,
      [proposalId]: newVotes,
    }));
  };

  const handleSubmit = async (proposal: DaoProposal) => {
    const payloadVotesMap = localVotes[proposal.id] || {};
    const totalSelected = Object.values(payloadVotesMap).reduce((s, v) => s + (v || 0), 0);

    if (totalSelected <= 0) return;
    if (totalSelected > votesAvailable) return;

    const votes: VotePayload['votes'] = Object.entries(payloadVotesMap)
      .filter(([, amount]) => amount > 0)
      .map(([optionId, amount]) => ({
        option_id: Number(optionId),
        amount,
      }));

    if (!votes.length) return;

    try {
      setSubmitting(true);
      const res = await fetch(`${API_BASE_URL}/api/dao/proposals/vote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          init_data: WebApp.initData,
          proposal_id: proposal.id,
          votes,
        }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();
      // ожидаем, что бэкенд вернёт обновлённый баланс пользователя
      if (typeof data.user_balance === 'number') {
        setVotesAvailable(data.user_balance);
      }

      setLocalVotes((prev) => ({
        ...prev,
        [proposal.id]: {},
      }));
    } catch (e) {
      console.error('Vote submit error', e);
      alert('Səsvermə zamanı xəta baş verdi. Bir az sonra yenidən cəhd edin.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="w-full min-h-screen bg-[#131f2f] flex items-center justify-center text-[#00f0ff]">
        Yüklənir...
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full min-h-screen bg-[#131f2f] flex items-center justify-center text-red-400 px-4 text-center">
        {error}
      </div>
    );
  }

  return (
    <div className="w-full min-h-screen bg-[#131f2f] text-[#e0f7ff] px-4 pt-6 pb-10">
      <h1 className="text-2xl font-bold mb-2 text-center">$GAP DAO</h1>
      <p className="text-sm text-center text-[#7ee9ff] mb-4">
        Səsvermədə səs çəkisi – balansınızdakı GAP sayına bərabərdir.
      </p>

      <div className="mb-4 text-center">
        <span className="text-sm text-[#7ee9ff]">Mövcud səs:</span>
        <div className="text-xl font-bold text-[#00f0ff]">
          {votesAvailable.toLocaleString('en-US')}
        </div>
      </div>

      {proposals.length === 0 && (
        <div className="text-center text-sm text-[#7ee9ff]">
          Hazırda aktiv səsvermə yoxdur.
        </div>
      )}

      <div className="space-y-6">
        {proposals.map((p) => {
          const myTotalForProposal = getProposalVotes(p.id);
          const now = new Date();
          const ends = new Date(p.ends_at);
          const ended = ends.getTime() < now.getTime();

          return (
            <div
              key={p.id}
              className="bg-[#0c1928] rounded-2xl p-4 shadow-lg border border-[#1f3b57]"
            >
              <div className="flex justify-between items-start gap-3 mb-2">
                <div>
                  <h2 className="text-lg font-semibold mb-1">{p.title}</h2>
                  <p className="text-xs text-[#9ed4ff] whitespace-pre-line">
                    {p.description}
                  </p>
                </div>
                <div className="text-right text-xs text-[#7ee9ff]">
                  <div>
                    Bitmə tarixi:{' '}
                    <span className="font-mono">
                      {ends.toLocaleString('ru-RU', {
                        day: '2-digit',
                        month: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                  <div className="mt-1">
                    Sənin səsin:{" "}
                    <span className="font-bold text-[#00f0ff]">
                      {myTotalForProposal}
                    </span>
                  </div>
                </div>
              </div>

              {/* пресеты процентов */}
              <div className="flex flex-wrap gap-1 mb-3">
                {PRESETS.map((pct) => (
                  <button
                    key={pct}
                    onClick={() => applyPreset(p.id, pct)}
                    className="px-2 py-1 rounded-full text-xs border border-[#1f3b57] text-[#7ee9ff] hover:bg-[#17324a] active:scale-95 transition"
                    type="button"
                  >
                    {pct === 0 ? '0%' : `${pct}%`}
                  </button>
                ))}
              </div>

              <div className="space-y-3">
                {p.options.map((opt) => {
                  const current = localVotes[p.id]?.[opt.id] || 0;

                  return (
                    <div
                      key={opt.id}
                      className="flex gap-3 items-center bg-[#0e1c2c] rounded-xl p-3 border border-[#1b3450]"
                    >
                      {/* картинка варианта */}
                      {opt.image_url && (
                        <div className="w-20 h-20 flex-shrink-0 rounded-lg overflow-hidden bg-[#050b12] border border-[#1f3b57]">
                          <img
                            src={opt.image_url}
                            alt={opt.title}
                            className="w-full h-full object-contain"
                          />
                        </div>
                      )}

                      <div className="flex-1 flex flex-col gap-2">
                        <div className="flex justify-between items-center">
                          <div>
                            <div className="font-semibold text-sm">{opt.title}</div>
                            {opt.description && (
                              <div className="text-[11px] text-[#9ed4ff] mt-0.5 whitespace-pre-line">
                                {opt.description}
                              </div>
                            )}
                          </div>
                          <div className="text-right text-[11px] text-[#7ee9ff]">
                            Ümumi səs:{" "}
                            <span className="font-mono">
                              {opt.total_votes.toLocaleString('en-US')}
                            </span>
                          </div>
                        </div>

                        <div className="flex items-center justify-between gap-2 mt-1">
                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              className="w-7 h-7 rounded-full bg-[#06111f] border border-[#1f3b57] flex items-center justify-center text-lg leading-none active:scale-95"
                              onClick={() => changeVote(p.id, opt.id, -1)}
                            >
                              −
                            </button>
                            <div className="px-2 py-1 rounded-lg bg-[#050b12] border border-[#1f3b57] text-xs font-mono min-w-[60px] text-center">
                              {current}
                            </div>
                            <button
                              type="button"
                              className="w-7 h-7 rounded-full bg-[#06111f] border border-[#1f3b57] flex items-center justify-center text-lg leading-none active:scale-95"
                              onClick={() => changeVote(p.id, opt.id, +1)}
                            >
                              +
                            </button>
                          </div>
                          <div className="text-[11px] text-[#7ee9ff]">
                            Sənin səsin bu variant üçün:{" "}
                            <span className="font-bold text-[#00f0ff]">
                              {current}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <button
                type="button"
                disabled={submitting || ended || getProposalVotes(p.id) <= 0}
                onClick={() => handleSubmit(p)}
                className={`mt-4 w-full py-2 rounded-xl text-sm font-semibold transition
                  ${
                    ended
                      ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
                      : submitting
                      ? 'bg-[#0d273d] text-[#7ee9ff] cursor-wait'
                      : getProposalVotes(p.id) > 0
                      ? 'bg-[#00f0ff] text-[#0e1a2b] hover:bg-[#7af9ff]'
                      : 'bg-[#0d273d] text-[#7ee9ff] cursor-not-allowed'
                  }`}
              >
                {ended
                  ? 'Səsvermə başa çatıb'
                  : getProposalVotes(p.id) > 0
                  ? 'Səs vermək'
                  : 'Səs seçin'}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default Governance;



