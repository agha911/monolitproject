import React, { useEffect, useState, useMemo } from "react";
import WebApp from "@twa-dev/sdk";
import { useTranslation } from "react-i18next";
import API_BASE_URL from "../config";

// ---- types ----

type DaoOption = {
  id: number;
  label: string;
  image_url?: string | null;
  total_votes: number;
};

type DaoProposal = {
  id: number;
  title: string;
  description: string;
  status: string;
  starts_at: string | null;
  ends_at: string | null;
  created_at: string;
  options: DaoOption[];
};

type VotePower = {
  total_power: number;
  available_power: number;
  used_power: number;
  locked_power: number;
};

type OptionVote = {
  option_id: number;
  votes: number;
};

const Governance: React.FC = () => {
  const { t } = useTranslation();

  const [proposal, setProposal] = useState<DaoProposal | null>(null);
  const [power, setPower] = useState<VotePower | null>(null);
  const [selectedVotes, setSelectedVotes] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const telegramUser = WebApp?.initDataUnsafe?.user;

  const totalSelected = useMemo(
    () => Object.values(selectedVotes).reduce((sum, v) => sum + (v || 0), 0),
    [selectedVotes]
  );

  const availablePower = power?.available_power ?? 0;

  // ----- helpers -----

  const getInitData = () => WebApp.initData || window.Telegram?.WebApp?.initData || "";

  const resetSelection = (opts: DaoOption[]) => {
    const initial: Record<number, number> = {};
    for (const o of opts) initial[o.id] = 0;
    setSelectedVotes(initial);
  };

  // применяем пресет (0/10/25/50/100% от доступной мощности)
  const applyPreset = (percent: number) => {
    if (!proposal || !power) return;
    if (percent <= 0) {
      resetSelection(proposal.options);
      return;
    }
    const targetTotal = Math.floor(availablePower * (percent / 100));
    if (targetTotal <= 0) {
      resetSelection(proposal.options);
      return;
    }

    const optionCount = proposal.options.length || 1;
    const basePerOption = Math.floor(targetTotal / optionCount);
    let remainder = targetTotal - basePerOption * optionCount;

    const next: Record<number, number> = {};
    for (const opt of proposal.options) {
      let v = basePerOption;
      if (remainder > 0) {
        v += 1;
        remainder -= 1;
      }
      next[opt.id] = v;
    }
    setSelectedVotes(next);
  };

  const handleChangeVotes = (optionId: number, delta: number) => {
    if (!power) return;
    setSelectedVotes((prev) => {
      const current = prev[optionId] || 0;
      let nextValue = current + delta;
      if (nextValue < 0) nextValue = 0;

      // не даём превысить availablePower суммарно
      const otherSum = Object.entries(prev)
        .filter(([id]) => Number(id) !== optionId)
        .reduce((sum, [, v]) => sum + (v || 0), 0);

      const maxForThis = Math.max(0, availablePower - otherSum);
      if (nextValue > maxForThis) nextValue = maxForThis;

      return { ...prev, [optionId]: nextValue };
    });
  };

  // ----- load data -----

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        setError(null);

        // 1. активные предложения
        const res = await fetch(`${API_BASE_URL}/api/dao/proposals/active`);
        if (!res.ok) {
          throw new Error(`active_proposals_http_${res.status}`);
        }
        const proposals: DaoProposal[] = await res.json();

        if (!proposals.length) {
          setProposal(null);
          setPower(null);
          setLoading(false);
          return;
        }

        const p = proposals[0];
        setProposal(p);
        resetSelection(p.options);

        // 2. голосовой вес пользователя
        const powerRes = await fetch(
          `${API_BASE_URL}/api/dao/proposals/${p.id}/power`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ init_data: getInitData() }),
          }
        );
        if (!powerRes.ok) {
          throw new Error(`power_http_${powerRes.status}`);
        }
        const powerData: VotePower = await powerRes.json();
        setPower(powerData);
      } catch (e) {
        console.error("Governance load error", e);
        setError(t("governance.error", { defaultValue: "Xəta baş verdi" }));
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [t]);

  const handleSubmit = async () => {
    if (!proposal || !power) return;
    const votes: OptionVote[] = Object.entries(selectedVotes)
      .map(([optionId, v]) => ({
        option_id: Number(optionId),
        votes: Number(v) || 0,
      }))
      .filter((v) => v.votes > 0);

    if (!votes.length) return;
    if (totalSelected > availablePower) return;

    try:
      setSubmitting(true);
      setError(null);

      const res = await fetch(
        `${API_BASE_URL}/api/dao/proposals/${proposal.id}/vote`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            init_data: getInitData(),
            option_votes: votes,
          }),
        }
      );
      if (!res.ok) {
        throw new Error(`vote_http_${res.status}`);
      }
      const data = await res.json();
      console.log("Vote result", data);

      // после голосования перезагружаем power и обнуляем локальный выбор
      const powerRes = await fetch(
        `${API_BASE_URL}/api/dao/proposals/${proposal.id}/power`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ init_data: getInitData() }),
        }
      );
      if (powerRes.ok) {
        const powerData: VotePower = await powerRes.json();
        setPower(powerData);
      }
      resetSelection(proposal.options);
    } catch (e) {
      console.error("Vote submit error", e);
      setError(t("governance.error", { defaultValue: "Xəta baş verdi" }));
    } finally {
      setSubmitting(false);
    }
  };

  // ----- render -----

  if (loading) {
    return (
      <div className="w-full min-h-screen flex items-center justify-center bg-[#131f2f] text-[#00f0ff]">
        {t("governance.loading", { defaultValue: "Yüklənir..." })}
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full min-h-screen flex flex-col items-center justify-center bg-[#131f2f] text-center text-[#00f0ff] px-4">
        <div className="text-lg font-semibold mb-2">
          {t("governance.error_title", { defaultValue: "Xəta baş verdi" })}
        </div>
        <div className="text-sm text-[#8bdcff] mb-4">
          {t("governance.error_subtitle", {
            defaultValue: "Bir az sonra yenidən yoxlayın.",
          })}
        </div>
        <button
          onClick={() => window.location.reload()}
          className="px-4 py-2 rounded-xl bg-[#00f0ff] text-[#0b1220] font-semibold"
        >
          {t("governance.retry", { defaultValue: "Yenidən cəhd et" })}
        </button>
      </div>
    );
  }

  if (!proposal) {
    return (
      <div className="w-full min-h-screen flex flex-col items-center justify-center bg-[#131f2f] text-center text-[#00f0ff] px-4">
        <div className="text-lg font-semibold mb-2">
          {t("governance.empty_title", {
            defaultValue: "Hazırda aktiv səsvermə yoxdur",
          })}
        </div>
        <div className="text-sm text-[#8bdcff]">
          {t("governance.empty_subtitle", {
            defaultValue: "Yeni səsvermələr tezliklə əlavə olunacaq.",
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="w-full min-h-screen bg-[#131f2f] text-[#00f0ff] px-4 py-6 flex flex-col items-center">
      <div className="w-full max-w-md">
        <h1 className="text-2xl font-bold mb-2 drop-shadow">
          {t("governance.title", { defaultValue: "Gappick DAO səsverməsi" })}
        </h1>
        <p className="text-sm text-[#8bdcff] mb-4">
          {proposal.title}
        </p>

        {/* power info */}
        {power && (
          <div className="mb-4 p-3 rounded-xl bg-[#0b1724] border border-[#1f3b57] text-xs text-[#a4e4ff]">
            <div className="flex justify-between mb-1">
              <span>{t("governance.power_total", { defaultValue: "Ümumi səs gücü" })}</span>
              <span>{power.total_power}</span>
            </div>
            <div className="flex justify-between mb-1">
              <span>{t("governance.power_available", { defaultValue: "Mövcud səs gücü" })}</span>
              <span>{power.available_power}</span>
            </div>
            <div className="flex justify-between">
              <span>{t("governance.power_used", { defaultValue: "Artıq istifadə olunub" })}</span>
              <span>{power.used_power}</span>
            </div>
          </div>
        )}

        {/* presets */}
        {power && (
          <div className="mb-4">
            <div className="text-xs text-[#8bdcff] mb-1">
              {t("governance.presets_label", {
                defaultValue: "Səs gücünü tez seç:",
              })}
            </div>
            <div className="flex flex-wrap gap-2">
              {[0, 10, 25, 50, 100].map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => applyPreset(p)}
                  className="px-2 py-1 rounded-full bg-[#0b1724] border border-[#1f3b57] text-xs hover:border-[#00f0ff] active:scale-95 transition"
                >
                  {p}%
                </button>
              ))}
            </div>
          </div>
        )}

        {/* options */}
        <div className="space-y-3 mb-4">
          {proposal.options.map((opt) => {
            const value = selectedVotes[opt.id] || 0;
            const imgSrc = opt.image_url || undefined;
            return (
              <div
                key={opt.id}
                className="p-3 rounded-xl bg-[#0b1724] border border-[#1f3b57] flex gap-3"
              >
                {imgSrc && (
                  <div className="w-16 h-16 rounded-lg overflow-hidden flex-shrink-0 border border-[#1f3b57] bg-black/40">
                    <img
                      src={imgSrc}
                      alt={opt.label}
                      className="w-full h-full object-cover"
                    />
                  </div>
                )}
                <div className="flex-1">
                  <div className="text-sm font-semibold mb-1">{opt.label}</div>
                  <div className="text-[11px] text-[#8bdcff] mb-2">
                    {t("governance.option_total_votes", {
                      defaultValue: "Toplam səs:",
                    })}{" "}
                    {opt.total_votes}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleChangeVotes(opt.id, -100)}
                      className="px-2 py-1 rounded-lg bg-[#09101b] text-xs"
                    >
                      -100
                    </button>
                    <button
                      type="button"
                      onClick={() => handleChangeVotes(opt.id, -10)}
                      className="px-2 py-1 rounded-lg bg-[#09101b] text-xs"
                    >
                      -10
                    </button>
                    <button
                      type="button"
                      onClick={() => handleChangeVotes(opt.id, -1)}
                      className="px-2 py-1 rounded-lg bg-[#09101b] text-xs"
                    >
                      -1
                    </button>

                    <div className="flex-1 text-center text-sm font-semibold">
                      {value}
                    </div>

                    <button
                      type="button"
                      onClick={() => handleChangeVotes(opt.id, +1)}
                      className="px-2 py-1 rounded-lg bg-[#09101b] text-xs"
                    >
                      +1
                    </button>
                    <button
                      type="button"
                      onClick={() => handleChangeVotes(opt.id, +10)}
                      className="px-2 py-1 rounded-lg bg-[#09101b] text-xs"
                    >
                      +10
                    </button>
                    <button
                      type="button"
                      onClick={() => handleChangeVotes(opt.id, +100)}
                      className="px-2 py-1 rounded-lg bg-[#09101b] text-xs"
                    >
                      +100
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* summary + submit */}
        {power && (
          <div className="mb-2 text-xs text-[#8bdcff]">
            {t("governance.total_selected", {
              defaultValue: "Seçilmiş səs sayı:",
            })}{" "}
            {totalSelected} / {availablePower}
          </div>
        )}

        <button
          type="button"
          disabled={submitting || !power || totalSelected <= 0 || totalSelected > availablePower}
          onClick={handleSubmit}
          className={`w-full py-2 mt-2 rounded-xl font-semibold ${
            submitting || !power || totalSelected <= 0 || totalSelected > availablePower
              ? "bg-[#1a2a3d] text-[#5d7c91] cursor-not-allowed"
              : "bg-[#00f0ff] text-[#0b1220] hover:opacity-90 active:scale-[0.98]"
          } transition`}
        >
          {submitting
            ? t("governance.submitting", { defaultValue: "Göndərilir..." })
            : t("governance.submit", { defaultValue: "Səs ver" })}
        </button>
      </div>
    </div>
  );
};

export default Governance;



