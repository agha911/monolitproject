// выдержка: меняем только то, что важно для стабильности

import React, { useState, useEffect, useMemo } from 'react';
import WebApp from '@twa-dev/sdk';
import { useTranslation } from 'react-i18next';
import MainButton from './MainButton';
import API_BASE_URL from './config';
import { useClickBuffer, FlushResponse } from '../hooks/useClickBuffer';
import { useAnimatedInt } from '../hooks/useAnimatedInt';

type ChallengeDay = {
  day_index: number;
  tiktok_url: string;
  question: string;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  reward_watch: number;
  reward_answer: number;
  is_active: boolean;
};

const Clicker: React.FC = () => {
  const { t } = useTranslation();

  const [telegramUser, setTelegramUser] = useState<any | null>(null);
  const [totalXp, setTotalXp] = useState(0);

  // авторитетная энергия (факт), из фронта и из onReconcile
  const [energy, setEnergy] = useState(1000);

  // плавное отрисовываемое значение
  const smoothEnergy = useAnimatedInt(energy, {
    speedPerUnit: 8,
    minDuration: 120,
    maxDuration: 600,
  });

  const [maxEnergy, setMaxEnergy] = useState(1000);
  const [lastEnergyUpdate, setLastEnergyUpdate] = useState<Date | null>(null);
  const [timeToFullEnergy, setTimeToFullEnergy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [clickBoost, setClickBoost] = useState(1);
  const [floatingTexts, setFloatingTexts] = useState<any[]>([]);
  const [serverSeq, setServerSeq] = useState<number | null>(null);
  const [seqReady, setSeqReady] = useState(false);

  // === challenge state ===
  const [challengeEnabled, setChallengeEnabled] = useState(false);
  const [challengeDays, setChallengeDays] = useState<ChallengeDay[]>([]);
  const [challengeLoading, setChallengeLoading] = useState(false);
  const [showChallenge, setShowChallenge] = useState(false);
  const [currentDayIndex, setCurrentDayIndex] = useState<number | null>(null);
  const [selectedOption, setSelectedOption] = useState<'A'|'B'|'C'|'D'|null>(null);
  const [watchRewardJustGot, setWatchRewardJustGot] = useState<number | null>(null);
  const [answerResult, setAnswerResult] = useState<{is_correct:boolean; reward_answer:number; codeword?:string|null} | null>(null);

  // прогресс и финал
  const [correctCount, setCorrectCount] = useState(0);
  const [finalReady, setFinalReady] = useState(false);
  const [showFinalModal, setShowFinalModal] = useState(false);
  const [finalKeywords, setFinalKeywords] = useState<string[]>(['','','','','']);
  const [finalSubmitState, setFinalSubmitState] = useState<{status:'idle'|'loading'|'success'|'error'; message?:string; reward?:number}>({status:'idle'});
  const [copied, setCopied] = useState(false);

  // --- challenge gating by Baku calendar ---
  const [nextRequiredDay, setNextRequiredDay] = useState<number | null>(null);
  const [secondsToNext, setSecondsToNext] = useState<number | null>(null);
  const [lockInfo, setLockInfo] = useState<{next:number|null}|null>(null);
  // ========================

  const fmtHMS = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const ss = s % 60;
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(ss).padStart(2,'0')}`;
  };

  useEffect(() => {
    if (secondsToNext == null) return;
    const id = setInterval(() => {
      setSecondsToNext((x) => (x == null ? null : Math.max(0, x - 1)));
    }, 1000);
    return () => clearInterval(id);
  }, [secondsToNext]);

  useEffect(() => {
    WebApp.ready();
    const user = WebApp.initDataUnsafe?.user;
    if (user) setTelegramUser(user);
    else alert('Xəta: Telegram istifadəçi məlumatlarını almaq mümkün olmadı.');
  }, []);

  const userId = telegramUser?.id ? String(telegramUser.id) : 'guest';
  const sessionId = useMemo(() => `${userId}-${Date.now()}`, [userId]);
  const seqStorageKey = useMemo(() => `gappick:lastSeq:${userId}`, [userId]);

  const initialLocalSeq = useMemo(() => {
    try {
      const saved = localStorage.getItem(seqStorageKey);
      return saved ? Number(saved) : 0;
    } catch {
      return 0;
    }
  }, [seqStorageKey]);

  useEffect(() => {
    if (!telegramUser) return;

    (async () => {
      try {
        await fetch(`${API_BASE_URL}/api/user/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });

        const res = await fetch(`${API_BASE_URL}/api/game/progress`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });

        const data = await res.json();

        setEnergy(data.energy);
        setTotalXp(data.total_xp ?? 0);
        setLastEnergyUpdate(data.lastEnergyUpdate ? new Date(data.lastEnergyUpdate) : null);
        setMaxEnergy(data.max_energy ?? 1000);
        setClickBoost((data.click_boost_level ?? 0) + 1);

        const s = Number(data.last_client_seq ?? 0);
        setServerSeq(s);
        try { localStorage.setItem(seqStorageKey, String(s)); } catch {}

        setSeqReady(true);
        setLoading(false);
      } catch (error) {
        console.error('İstifadəçinin ilkinləşdirilməsində xəta:', error);
        setSeqReady(false);
      }
    })();
  }, [telegramUser, seqStorageKey]);

  // yumşaq auto-refresh enerji
  useEffect(() => {
    const interval = setInterval(async () => {
      if (!telegramUser || energy >= maxEnergy) return;
      try {
        const res = await fetch(`${API_BASE_URL}/api/game/progress`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });

        const data = await res.json();
        setEnergy(data.energy);
        setLastEnergyUpdate(data.lastEnergyUpdate ? new Date(data.lastEnergyUpdate) : null);
        setMaxEnergy(data.max_energy ?? 1000);
        setClickBoost((data.click_boost_level ?? 0) + 1);

        const s = Number(data.last_client_seq ?? 0);
        if (serverSeq === null || s > serverSeq) {
          setServerSeq(s);
          try { localStorage.setItem(seqStorageKey, String(s)); } catch {}
          setSeqReady(true);
        }
      } catch (err) {
        console.error('Auto yeniləmədə xəta:', err);
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [telegramUser, energy, maxEnergy, serverSeq, seqStorageKey]);

  // tam bərpaya qədər taymer
  useEffect(() => {
    const interval = setInterval(() => {
      if (!lastEnergyUpdate || energy >= maxEnergy) {
        setTimeToFullEnergy(null);
        return;
      }
      const now = new Date();
      const msPassed = now.getTime() - (lastEnergyUpdate?.getTime?.() ?? 0);
      const totalRecoveryMinutes = 480;
      const intervalMsPerUnit = (totalRecoveryMinutes / maxEnergy) * 60 * 1000;
      const remainingUnits = maxEnergy - energy;
      const msToNextUnit = intervalMsPerUnit - (msPassed % intervalMsPerUnit);
      const msToFull = (remainingUnits - 1) * intervalMsPerUnit + msToNextUnit;
      const totalSeconds = Math.max(0, Math.ceil(msToFull / 1000));
      const hours = Math.floor(totalSeconds / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = totalSeconds % 60;
      const hh = hours.toString().padStart(2, '0');
      const mm = minutes.toString().padStart(2, '0');
      const ss = seconds.toString().padStart(2, '0');
      setTimeToFullEnergy(`${hh}:${mm}:${ss}`);
    }, 1000);

    return () => clearInterval(interval);
  }, [lastEnergyUpdate, energy, maxEnergy]);

  const onReconcile = async (data: FlushResponse) => {
    if (data.status === "ok") {
      setEnergy(data.energy);
      setTotalXp(data.total_xp);
      setServerSeq(Number(data.server_seq ?? 0));
    } else if (data.status === "noop") {
      return;
    } else {
      try {
        const res = await fetch(`${API_BASE_URL}/api/game/progress`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ init_data: WebApp.initData }),
        });
        const p = await res.json();
        setEnergy(p.energy);
        setTotalXp(p.total_xp ?? 0);
        setLastEnergyUpdate(p.lastEnergyUpdate ? new Date(p.lastEnergyUpdate) : null);
        setMaxEnergy(p.max_energy ?? 1000);
        setClickBoost((p.click_boost_level ?? 0) + 1);
        setServerSeq(Number(p.last_client_seq ?? 0));
      } catch (e) {
        console.warn("Xəta sonrası yeniləmə alınmadı", e);
      }
    }
  };

  const { addClicks } = useClickBuffer({
    initData: WebApp.initData,
    sessionId,
    onReconcile,
    enabled: seqReady && !!telegramUser,
    flushEveryMs: 200,
    threshold: 50,
    initialSeq: Math.max(serverSeq ?? 0, initialLocalSeq),
    maxBatch: 50,
    lockKey: userId,
    seqStorageKey: seqStorageKey as any,
    canSend: energy > 0
  });

  const handleMultiClick = (x: number, y: number) => {
    if (!telegramUser || loading || energy <= 0) return;
    const spend = Math.min(clickBoost, energy);
    if (spend <= 0) return;

    setTotalXp((prev) => prev + spend);
    setEnergy((prev) => Math.max(0, prev - spend));

    const id = Date.now() + Math.random();
    setFloatingTexts((prev) => [...prev, { id, value: spend, x, y }]);
    setTimeout(() => {
      setFloatingTexts((prev) => prev.filter((t) => t.id !== id));
    }, 1000);

    addClicks(spend);
  };

  // === challenge: yükləmə və cari gün seçimi ===
  useEffect(() => {
    if (!telegramUser) return;

    (async () => {
      try {
        setChallengeLoading(true);
        const [cfgRes, prgRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/challenge/config`),
          fetch(`${API_BASE_URL}/api/challenge/progress?telegram_id=${telegramUser.id}`)
        ]);
        const cfg = await cfgRes.json();
        const prg = await prgRes.json();

        setChallengeEnabled(!!cfg.enabled);
        setChallengeDays(Array.isArray(cfg.days) ? cfg.days : []);

        // neçə düzgün cavab var
        const correct = (prg.days || []).filter((d: any) => d.is_correct === true).length;
        setCorrectCount(correct);
        setFinalReady(!!prg.final_ready);

        // 🔹 Жёсткая привязка к бэку:
        const nx = Number(prg.next_required_day ?? 0) || null;
        setNextRequiredDay(nx);
        setCurrentDayIndex(nx);
        setSecondsToNext(typeof prg.seconds_to_next_day === 'number' ? prg.seconds_to_next_day : null);
      } catch (e) {
        console.warn('challenge init failed', e);
      } finally {
        setChallengeLoading(false);
      }
    })();
  }, [telegramUser]);

  const currentDay: ChallengeDay | null = useMemo(() => {
    if (!currentDayIndex) return null;
    return challengeDays.find(d => d.day_index === currentDayIndex) || null;
  }, [currentDayIndex, challengeDays]);

  const energyInt = Math.floor(smoothEnergy);
  const energyProgress = Math.min((smoothEnergy / maxEnergy) * 100, 100);

  // === challenge: əməliyyatlar ===
  const handleWatch = async () => {
    if (!telegramUser || !currentDayIndex) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/challenge/watch`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ telegram_id: telegramUser.id, day_index: currentDayIndex })
      });

      if (res.status === 409) {
        const j = await res.json().catch(() => ({}));
        const n = j?.detail?.next_required_day ?? null;
        setLockInfo({ next: n ?? null });
        try {
          const prgRes = await fetch(`${API_BASE_URL}/api/challenge/progress?telegram_id=${telegramUser.id}`);
          const prg = await prgRes.json();
          const nx = Number(prg.next_required_day ?? 0) || null;
          setNextRequiredDay(nx);
          setCurrentDayIndex(nx);
          setSecondsToNext(typeof prg.seconds_to_next_day === 'number' ? prg.seconds_to_next_day : null);
        } catch {}
        return;
      }

      const data = await res.json();
      setWatchRewardJustGot(data?.reward_watch ?? 0);
      if (typeof data?.reward_watch === 'number' && data.reward_watch > 0) {
        setTotalXp(prev => prev + data.reward_watch);
      }
    } catch (e) {
      console.warn('watch failed', e);
    }
  };

  const handleAnswer = async () => {
    if (!telegramUser || !currentDayIndex || !selectedOption || answerResult) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/challenge/answer`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          telegram_id: telegramUser.id,
          day_index: currentDayIndex,
          selected_option: selectedOption
        })
      });

      if (res.status === 409) {
        const j = await res.json().catch(() => ({}));
        const n = j?.detail?.next_required_day ?? null;
        setLockInfo({ next: n ?? null });
        try {
          const prgRes = await fetch(`${API_BASE_URL}/api/challenge/progress?telegram_id=${telegramUser.id}`);
          const prg = await prgRes.json();
          const nx = Number(prg.next_required_day ?? 0) || null;
          setNextRequiredDay(nx);
          setSecondsToNext(typeof prg.seconds_to_next_day === 'number' ? prg.seconds_to_next_day : null);
        } catch {}
        return;
      }

      const data = await res.json();
      setAnswerResult({
        is_correct: !!data?.is_correct,
        reward_answer: Number(data?.reward_answer ?? 0),
        codeword: data?.codeword ?? null
      });
      if (Number(data?.reward_answer ?? 0) > 0) {
        setTotalXp(prev => prev + Number(data.reward_answer));
      }

      // progress refresh (final və s.)
      try {
        const prgRes = await fetch(`${API_BASE_URL}/api/challenge/progress?telegram_id=${telegramUser.id}`);
        const prg = await prgRes.json();
        const correct = (prg.days || []).filter((d: any) => d.is_correct === true).length;
        setCorrectCount(correct);
        setFinalReady(!!prg.final_ready);
        const nx = Number(prg.next_required_day ?? 0) || null;
        setNextRequiredDay(nx);
        setSecondsToNext(typeof prg.seconds_to_next_day === 'number' ? prg.seconds_to_next_day : null);
      } catch {}
    } catch (e) {
      console.warn('answer failed', e);
    }
  };

  // === final tapşırıq ===
  const submitFinal = async () => {
    if (!telegramUser) return;
    if (finalKeywords.some(k => !k.trim())) {
      setFinalSubmitState({status:'error', message:'Bütün 5 xanı doldurun'});
      return;
    }
    try {
      setFinalSubmitState({status:'loading'});
      const res = await fetch(`${API_BASE_URL}/api/challenge/final/submit`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ telegram_id: telegramUser.id, keywords: finalKeywords })
      });
      const data = await res.json();
      if (data?.success) {
        const reward = Number(data?.reward ?? 0);
        if (reward > 0) setTotalXp(prev => prev + reward);
        setFinalSubmitState({status:'success', message:'Uğurlu! Mükafat verildi.', reward});
      } else {
        setFinalSubmitState({status:'error', message:'Sözlər düzgün deyil. Yenidən cəhd edin.'});
      }
    } catch (e) {
      setFinalSubmitState({status:'error', message:'Göndərmə xətası. Bir az sonra yenidən cəhd edin.'});
    }
  };
  // ==========================

  return (
    <div className="w-full min-h-screen bg-[#131f2f] text-center flex flex-col items-center justify-start pt-8 px-4 text-[#00f0ff]">
      <h2 className="text-2xl font-bold mb-2 drop-shadow-md">$GAP: {totalXp}</h2>
      <div className="text-sm text-[#7ee9ff] mb-2">x{clickBoost} boost</div>

      <div className="my-4 w-full max-w-md">
        <label className="block mb-1 text-sm text-[#7ee9ff]">
          {t('energy')}: {Math.floor(smoothEnergy)} / {maxEnergy}
        </label>
        <div className="w-full h-4 bg-[#0d273d] rounded overflow-hidden shadow-inner">
          <div
            className="h-full bg-gradient-to-r from-[#7af9ff] to-[#00f0ff]"
            style={{ width: `${Math.min((smoothEnergy / maxEnergy) * 100, 100)}%`, transition: "none" }}
          />
        </div>
        {energy < maxEnergy && timeToFullEnergy && (
          <p className="text-xs mt-1 text-[#89dfff]">
            {t('full_in')} {timeToFullEnergy}
          </p>
        )}
      </div>

      <div className="relative w-96 h-96 mt-6">
        <div className="absolute inset-0 flex items-center justify-center">
          <MainButton energy={Math.floor(smoothEnergy)} onMultiClick={handleMultiClick} />
        </div>

        {floatingTexts.map((text) => (
          <div
            key={text.id}
            className="absolute text-lg font-bold text-yellow-300"
            style={{
              left: `${text.x}%`,
              top: `${text.y}%`,
              transform: 'translate(-50%, -50%)',
              pointerEvents: 'none',
              animation: 'floatUpFade 1s ease-out',
            }}
          >
            +{text.value}
          </div>
        ))}

        <style>{`
          @keyframes floatUpFade {
            0% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
            100% { opacity: 0; transform: translate(-50%, -100%) scale(1.2); }
          }
        `}</style>
      </div>

      {/* loader */}
      {challengeLoading && (
        <div className="mt-3 text-xs text-[#89dfff] animate-pulse">Tapşırıq yüklənir…</div>
      )}

      {/* button under clicker */}
      {challengeEnabled && !challengeLoading && currentDayIndex && (
        <>
          <button
            className="mt-4 px-4 py-2 rounded-xl bg-[#0d273d] text-[#7ee9ff] border border-[#1f3b57] shadow relative"
            onClick={() => { setShowChallenge(true); setAnswerResult(null); setWatchRewardJustGot(null); setCopied(false); setLockInfo(null); }}
          >
            🎥 Günün tapşırığı
            <span className="ml-2 text-[11px] px-2 py-0.5 rounded-full bg-[#10263d] border border-[#1f3b57] text-[#89dfff] align-middle">
              {correctCount}/5
            </span>
          </button>
          {lockInfo && secondsToNext != null && (
            <div className="mt-2 text-[11px] text-[#ffb3b3]">
              Bu gün üçün tapşırıq kilidlidir. Növbəti açılacaq: Gün {lockInfo.next ?? '-'} — {fmtHMS(secondsToNext)} qalıb.
            </div>
          )}
        </>
      )}

      {/* final button */}
      {challengeEnabled && !challengeLoading && finalReady && (
        <button
          className="mt-2 px-4 py-2 rounded-xl bg-[#00f0ff] text-[#0b1a28] font-semibold shadow"
          onClick={() => { setShowFinalModal(true); setFinalSubmitState({status:'idle'}); }}
        >
          ⭐ Final tapşırıq
        </button>
      )}

      {/* daily modal */}
      {showChallenge && currentDay && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-[92%] max-w-md bg-[#0e1b2a] text-[#c9f6ff] rounded-2xl p-4 shadow-2xl">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg font-bold">Günün tapşırığı — Gün {currentDay.day_index}</h3>
              <button
                className="text-[#89dfff] hover:text-white"
                onClick={() => setShowChallenge(false)}
              >
                ✖
              </button>
            </div>

            <a
              className="inline-block mb-3 text-[#00f0ff] underline"
              href={currentDay.tiktok_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              TikTok videosunu aç
            </a>

            <div className="mb-3">
              <button
                className="px-3 py-2 rounded-lg bg-[#10263d] border border-[#1f3b57]"
                onClick={handleWatch}
                disabled={watchRewardJustGot !== null}
              >
                Videoya baxdım
              </button>
              {watchRewardJustGot !== null && (
                <div className="text-xs mt-1 text-[#7ee9ff]">
                  Baxış mükafatı: +{watchRewardJustGot} GAP
                </div>
              )}
            </div>

            <div className="text-left">
              <div className="font-semibold mb-2">{currentDay.question}</div>
              {(['A','B','C','D'] as const).map((k) => {
                const label =
                  k === 'A' ? currentDay.option_a :
                  k === 'B' ? currentDay.option_b :
                  k === 'C' ? currentDay.option_c :
                               currentDay.option_d;
                return (
                  <label key={k} className="flex items-center gap-2 mb-2 cursor-pointer">
                    <input
                      type="radio"
                      name="challenge_option"
                      value={k}
                      checked={selectedOption === k}
                      onChange={() => setSelectedOption(k)}
                      disabled={!!answerResult}
                    />
                    <span>{label}</span>
                  </label>
                );
              })}
            </div>

            <div className="mt-3 flex gap-2">
              <button
                className="flex-1 px-3 py-2 rounded-lg bg-[#00f0ff] text-[#0b1a28] font-semibold disabled:opacity-50"
                onClick={handleAnswer}
                disabled={!selectedOption || !!answerResult}
              >
                Cavab ver
              </button>
            </div>

            {answerResult && (
              <div className="mt-3 text-sm">
                <div className={answerResult.is_correct ? 'text-green-400' : 'text-red-300'}>
                  {answerResult.is_correct ? 'Doğru!' : 'Səhv'}
                </div>
                <div className="text-[#7ee9ff]">
                  Cavab üçün mükafat: +{answerResult.reward_answer} GAP
                </div>

                {answerResult.codeword && (
                  <div className="mt-2">
                    Şifrə sözü: <span className="font-bold">{answerResult.codeword}</span>
                  </div>
                )}

                <div className="mt-3 flex gap-2">
                  {answerResult.codeword && (
                    <button
                      className="px-3 py-2 rounded-lg bg-[#10263d] border border-[#1f3b57]"
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(answerResult.codeword as string);
                          setCopied(true);
                          setTimeout(() => setCopied(false), 1500);
                        } catch {}
                      }}
                    >
                      {copied ? 'Kopyalandı!' : 'Kopyala'}
                    </button>
                  )}

                  <button
                    className="flex-1 px-3 py-2 rounded-lg bg-[#00f0ff] text-[#0b1a28] font-semibold"
                    onClick={() => {
                      setShowChallenge(false);
                      setSelectedOption(null);
                      setWatchRewardJustGot(null);
                      setAnswerResult(null);
                      setCopied(false);
                      setCurrentDayIndex(null); // növbəti günə qədər gizlə
                      setLockInfo(null);
                    }}
                  >
                    Bağla
                  </button>
                </div>
              </div>
            )}

            {/* Если модалка открыта, но день закрыт (например, пришел 409 до этого) */}
            {lockInfo && secondsToNext != null && (
              <div className="mt-3 text-[12px] text-center text-[#ffb3b3]">
                Bu gün üçün tapşırıq kilidlidir. Növbəti açılacaq: Gün {lockInfo.next ?? '-'} — {fmtHMS(secondsToNext)} qalıb.
              </div>
            )}
          </div>
        </div>
      )}
      {/* end daily modal */}

      {/* final modal */}
      {showFinalModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-[92%] max-w-md bg-[#0e1b2a] text-[#c9f6ff] rounded-2xl p-4 shadow-2xl">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-bold">Final tapşırıq</h3>
              <button
                className="text-[#89dfff] hover:text-white"
                onClick={() => setShowFinalModal(false)}
              >
                ✖
              </button>
            </div>

            <p className="text-sm text-[#89dfff] mb-3">
              5 şifrə sözünü ardıcıllıqla daxil edin (Gün 1 → Gün 5).
            </p>

            <div className="grid grid-cols-1 gap-2">
              {finalKeywords.map((val, i) => (
                <input
                  key={i}
                  type="text"
                  value={val}
                  onChange={(e) => {
                    const next = [...finalKeywords];
                    next[i] = e.target.value;
                    setFinalKeywords(next);
                  }}
                  placeholder={`Söz ${i+1}`}
                  className="w-full px-3 py-2 rounded-lg bg-[#0d273d] border border-[#1f3b57] outline-none"
                />
              ))}
            </div>

            <div className="mt-3 flex gap-2">
              <button
                className="flex-1 px-3 py-2 rounded-lg bg-[#00f0ff] text-[#0b1a28] font-semibold disabled:opacity-50"
                onClick={submitFinal}
                disabled={finalSubmitState.status === 'loading'}
              >
                {finalSubmitState.status === 'loading' ? 'Yoxlanılır…' : 'Göndər'}
              </button>
              <button
                className="px-3 py-2 rounded-lg bg-[#10263d] border border-[#1f3b57]"
                onClick={() => setShowFinalModal(false)}
              >
                Sonra
              </button>
            </div>

            {finalSubmitState.status !== 'idle' && (
              <div className="mt-3 text-sm">
                {finalSubmitState.status === 'success' && (
                  <div className="text-green-400">
                    {finalSubmitState.message} {finalSubmitState.reward ? `( +${finalSubmitState.reward} GAP )` : null}
                  </div>
                )}
                {finalSubmitState.status === 'error' && (
                  <div className="text-red-300">
                    {finalSubmitState.message || 'Xəta.'}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
      {/* end final modal */}
    </div>
  );
};

export default Clicker;























































































