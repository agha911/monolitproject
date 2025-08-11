import { useEffect, useRef, useState } from "react";
import API_BASE_URL from "../components/config";

export type FlushResponse = {
  status: "ok" | "noop" | string;
  accepted_clicks: number;
  energy: number;
  total_xp: number;
  daily_progress: number;
  server_seq: number;
  task_completed: boolean;
};

type Options = {
  initData?: string;
  sessionId: string;
  onReconcile: (r: FlushResponse) => void;
  flushEveryMs?: number;
  threshold?: number;
  initialSeq?: number;
  maxBatch?: number;
  enabled?: boolean;
};

export function useClickBuffer({
  initData,
  sessionId,
  onReconcile,
  flushEveryMs = 250,
  threshold = 20,
  initialSeq = 0,
  maxBatch = 50,
  enabled = true,
}: Options) {
  const [buffered, setBuffered] = useState(0);

  const inflight = useRef(false);
  const seqRef = useRef<number>(initialSeq);
  const currentBatch = useRef<{ seq: number; amount: number } | null>(null);
  const retryTimer = useRef<number | null>(null);
  const bufferedRef = useRef(0);

  // держим актуальное значение буфера в ref для интервала
  useEffect(() => {
    bufferedRef.current = buffered;
  }, [buffered]);

  // если initialSeq подрос — подтягиваем локальный
  useEffect(() => {
    if (typeof initialSeq === "number" && initialSeq > seqRef.current) {
      seqRef.current = initialSeq;
    }
  }, [initialSeq]);

  const resolveInitData = () => {
    if (initData && initData.length > 0) return initData;
    if (typeof window !== "undefined") {
      const w = window as any;
      const raw = w?.Telegram?.WebApp?.initData;
      if (raw && typeof raw === "string" && raw.length > 0) return raw;
    }
    return "";
  };

  const addClicks = (n = 1) => {
    if (n <= 0) return;
    setBuffered((v) => v + n);
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

  const clearRetry = () => {
    if (retryTimer.current) {
      window.clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
  };

  const scheduleRetry = (ms = 120) => {
    clearRetry();
    retryTimer.current = window.setTimeout(() => {
      void flush();
    }, ms) as unknown as number;
  };

  const flush = async () => {
    if (!enabled) return;
    if (inflight.current) return;

    // сформировать батч из актуального буфера
    if (!currentBatch.current) {
      const amount = Math.max(1, Math.min(bufferedRef.current, maxBatch));
      if (amount <= 0) return;
      currentBatch.current = { seq: seqRef.current + 1, amount };
    }

    const { seq, amount } = currentBatch.current;
    inflight.current = true;

    try {
      const data = await postBatch(seq, amount);

      // серверный seq — истина в последней инстанции
      const srvSeq = Number(data.server_seq ?? seq);
      if (!Number.isNaN(srvSeq) && srvSeq >= seqRef.current) {
        seqRef.current = srvSeq;
      }

      if (data.status === "ok") {
        const accepted = Math.max(0, Math.min(amount, Number(data.accepted_clicks) || 0));

        // уменьшаем буфер только на действительно принятые клики
        if (accepted > 0) {
          setBuffered((v) => Math.max(0, v - accepted));
        }

        // отдать состояние наверх (важно даже при accepted=0)
        onReconcile(data);

        currentBatch.current = null;
        inflight.current = false;

        // если энергии нет или ничего не приняли — не долбим сразу
        if ((Number(data.energy) || 0) === 0 || accepted === 0) {
          scheduleRetry(600); // мягкий бэкофф при пустом принятии/нулевой энергии
        } else if (bufferedRef.current > 0) {
          scheduleRetry(0); // есть ещё буфер — шлём сразу
        }
      } else if (data.status === "noop") {
        // noop: не трогаем буфер, но пробрасываем наверх (могла восстановиться энергия)
        onReconcile(data);

        inflight.current = false;
        // повторим тот же amount, но с новым seq
        currentBatch.current = { seq: seqRef.current + 1, amount };
        scheduleRetry(80);
      } else {
        // любой другой статус — мягкий ретрай без изменений
        inflight.current = false;
        scheduleRetry(300);
      }
    } catch {
      inflight.current = false;
      scheduleRetry(400);
    }
  };

  // периодический пульс — не завязываем на buffered, читаем bufferedRef
  useEffect(() => {
    if (!enabled) return;
    const t = window.setInterval(() => {
      if (!inflight.current && bufferedRef.current > 0) void flush();
    }, flushEveryMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flushEveryMs, enabled, maxBatch]);

  // моментальный старт при достижении порога
  useEffect(() => {
    if (!enabled) return;
    if (buffered >= threshold && !inflight.current && !currentBatch.current) {
      void flush();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buffered, threshold, enabled]);

  // beacons на скрытие/уход со страницы
  useEffect(() => {
    if (!enabled) return;

    const handler = () => {
      if (bufferedRef.current <= 0) return;
      if (inflight.current) return; // не нарушаем порядок

      const rawInit = resolveInitData();
      if (!rawInit || !sessionId) return;

      const amount = Math.max(1, Math.min(bufferedRef.current, maxBatch));
      const beacon = {
        init_data: rawInit,
        delta_clicks: amount,
        client_seq: seqRef.current + 1,
        session_id: sessionId,
      };

      try {
        navigator.sendBeacon(
          `${API_BASE_URL}/api/game/clicks/flush`,
          new Blob([JSON.stringify(beacon)], { type: "application/json" })
        );
        // локально буфер не трогаем — доживём до следующего запуска
      } catch {
        // ignore
      }
    };

    const visibilityHandler = () => {
      if (document.visibilityState === "hidden") handler();
    };

    window.addEventListener("beforeunload", handler);
    document.addEventListener("visibilitychange", visibilityHandler);
    return () => {
      window.removeEventListener("beforeunload", handler);
      document.removeEventListener("visibilitychange", visibilityHandler);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, maxBatch, initData, enabled]);

  // общий cleanup ретраев
  useEffect(() => () => clearRetry(), []);

  const forceFlush = () => { void flush(); };

  return { addClicks, forceFlush, buffered, lastSeq: seqRef.current };
}







