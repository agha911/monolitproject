import { useEffect, useRef, useState } from "react";
import API_BASE_URL from "../components/config";

export type FlushResponse = {
  status: string;
  accepted_clicks: number;
  energy: number;
  total_xp: number;
  daily_progress: number;
  server_seq: number;
  task_completed: boolean;
};

type Options = {
  initData?: string;          // Telegram WebApp.initData
  sessionId: string;
  onReconcile: (r: FlushResponse) => void;

  // Тюнинг
  enabled?: boolean;          // можно включать/выключать флаш после sync seq
  flushEveryMs?: number;      // debounce-интервал
  threshold?: number;         // когда буфер >= threshold — шлём сразу
  initialSeq?: number;        // начальный last_client_seq с бэка
  maxBatch?: number;          // лимит бэка (MAX_DELTA_PER_FLUSH)
};

export function useClickBuffer({
  initData,
  sessionId,
  onReconcile,
  enabled = true,
  flushEveryMs = 200,
  threshold = 50,
  initialSeq = 0,
  maxBatch = 50,
}: Options) {
  const [buffered, _setBuffered] = useState(0);

  const inflight = useRef(false);
  const seqRef = useRef<number>(initialSeq);
  const timerRef = useRef<number | null>(null);
  const retryTimer = useRef<number | null>(null);
  const currentBatch = useRef<{ seq: number; amount: number } | null>(null);
  const beaconLockUntil = useRef<number>(0);

  // держим актуальное значение буфера в ref, чтобы избежать «захвата» старого значения в замыканиях
  const bufferedRef = useRef(0);
  const setBuffered = (fnOrVal: number | ((v: number) => number)) => {
    _setBuffered((prev) => {
      const next = typeof fnOrVal === "function" ? (fnOrVal as (v: number) => number)(prev) : fnOrVal;
      bufferedRef.current = next;
      return next;
    });
  };

  // если initialSeq подтянули после /progress — обновим локальный seq
  useEffect(() => {
    if (typeof initialSeq === "number" && initialSeq > seqRef.current) {
      seqRef.current = initialSeq;
    }
  }, [initialSeq]);

  // утилиты
  const nowMs = () => (typeof performance !== "undefined" ? performance.now() : Date.now());

  const resolveInitData = () => {
    if (initData && initData.length > 0) return initData;
    if (typeof window !== "undefined") {
      const w = window as any;
      const raw = w?.Telegram?.WebApp?.initData;
      if (raw && typeof raw === "string" && raw.length > 0) return raw;
    }
    return "";
  };

  const postBatch = async (seq: number, amount: number) => {
    const safeSeq = Math.max(1, Math.floor(seq));
    const safeAmount = Math.max(1, Math.min(Math.floor(amount), maxBatch));
    const rawInit = resolveInitData();

    if (!rawInit || !sessionId) {
      throw new Error("flush blocked: missing init_data or session_id");
    }

    const payload = {
      init_data: rawInit,
      delta_clicks: safeAmount,
      client_seq: safeSeq,
      session_id: sessionId,
    };

    const resp = await fetch(`${API_BASE_URL}/api/game/clicks/flush`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`flush failed ${resp.status}: ${text}`);
    }
    return (await resp.json()) as FlushResponse;
  };

  const schedule = (delay = flushEveryMs) => {
    if (timerRef.current != null) return;
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      void drainOnce();
    }, delay) as unknown as number;
  };

  const cancelTimers = () => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (retryTimer.current != null) {
      window.clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
  };

  const drainOnce = async () => {
    if (!enabled) return;
    if (inflight.current) return;

    // защитимся от гонки с недавним sendBeacon
    if (nowMs() < beaconLockUntil.current) return;

    const available = bufferedRef.current;
    if (available <= 0) return;

    // используем один «текущий» батч, пока он не доотправится/не ретрайнется
    if (!currentBatch.current) {
      const seq = seqRef.current + 1;
      const amount = Math.min(available, maxBatch);
      currentBatch.current = { seq, amount };
    }

    inflight.current = true;
    const { seq, amount } = currentBatch.current;

    try {
      const data = await postBatch(seq, amount);

      // сколько реально засчитал сервер (может быть меньше в будущем, если введёте серверные лимиты)
      const accepted = Math.max(0, Math.min(amount, Number(data.accepted_clicks ?? amount)));

      // уменьшаем буфер на принятую часть
      setBuffered((v) => Math.max(0, v - accepted));

      // важная синхронизация seq: берём максимум из локального seq и server_seq
      const serverSeq = Number(data.server_seq ?? 0);
      seqRef.current = Math.max(seqRef.current, serverSeq, seq);

      currentBatch.current = null;
      inflight.current = false;

      onReconcile(data);

      // если ещё есть в буфере — продолжим без дебаунса (быстро «выгрызем» очередь)
      if (bufferedRef.current >= maxBatch) {
        // немедленно следующая посылка
        void drainOnce();
      } else if (bufferedRef.current > 0) {
        // немного подождём, вдруг пользователь перестанет кликать
        schedule(flushEveryMs);
      }
    } catch (e) {
      inflight.current = false;
      // попробуем тот же батч ещё раз
      if (retryTimer.current) window.clearTimeout(retryTimer.current);
      retryTimer.current = window.setTimeout(() => {
        void drainOnce();
      }, 400) as unknown as number;
    }
  };

  // публичный метод для добавления «сырых» кликов (у тебя это = spend = boost)
  const addClicks = (n = 1) => {
    if (!enabled) return;
    if (n <= 0) return;
    setBuffered((v) => v + n);

    // если буфер вырос до порога — отправим сразу
    if (!inflight.current && bufferedRef.current >= threshold) {
      cancelTimers();
      void drainOnce();
    } else {
      // иначе просто задебаунсим
      schedule(flushEveryMs);
    }
  };

  // попытка сохранить клики при закрытии/сворачивании
  useEffect(() => {
    const handler = () => {
      if (!enabled) return;
      const left = bufferedRef.current;
      if (left <= 0) return;

      const rawInit = resolveInitData();
      if (!rawInit || !sessionId) return;

      const amount = Math.min(left, maxBatch);
      const beacon = {
        init_data: rawInit,
        delta_clicks: amount,
        client_seq: seqRef.current + 1,
        session_id: sessionId,
      };
      try {
        // небольшой «лок» на конкурентные обычные флаши
        beaconLockUntil.current = nowMs() + 800;
        cancelTimers();
        navigator.sendBeacon(
          `${API_BASE_URL}/api/game/clicks/flush`,
          new Blob([JSON.stringify(beacon)], { type: "application/json" })
        );
        // не трогаем локальный буфер — если бэкон не дойдёт, обычный ретрай догрызёт
      } catch {
        // ignore
      }
    };

    const vis = () => {
      if (document.visibilityState === "hidden") handler();
    };

    window.addEventListener("beforeunload", handler);
    document.addEventListener("visibilitychange", vis);
    return () => {
      window.removeEventListener("beforeunload", handler);
      document.removeEventListener("visibilitychange", vis);
    };
  }, [enabled, sessionId, maxBatch, initData, flushEveryMs]);

  // если включили/выключили — почистим таймеры
  useEffect(() => {
    if (!enabled) cancelTimers();
  }, [enabled]);

  return {
    addClicks,
    forceFlush: () => { cancelTimers(); void drainOnce(); },
    buffered,
    lastSeq: seqRef.current,
  };
}





