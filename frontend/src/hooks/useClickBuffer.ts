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
  enabled?: boolean; // включение/выключение автофлаша
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

  useEffect(() => {
    if (typeof initialSeq === "number" && initialSeq > seqRef.current) {
      seqRef.current = initialSeq;
    }
  }, [initialSeq]);

  const resolveInitData = () => {
    if (initData && initData.length > 0) return initData;
    if (typeof window !== "undefined") {
      const w = (window as any);
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

  const scheduleRetry = (ms = 120) => {
    if (retryTimer.current) window.clearTimeout(retryTimer.current);
    retryTimer.current = window.setTimeout(() => {
      void flush();
    }, ms) as unknown as number;
  };

  const flush = async () => {
    if (!enabled) return;
    if (inflight.current) return;

    if (!currentBatch.current) {
      if (buffered <= 0) return;
      currentBatch.current = {
        seq: seqRef.current + 1,
        amount: Math.max(1, Math.min(buffered, maxBatch)),
      };
    }

    const { seq, amount } = currentBatch.current;
    inflight.current = true;

    try {
      const data = await postBatch(seq, amount);

      // ВАЖНО:
      //  - при "ok" вычитаем из буфера ИМЕННО accepted_clicks
      //  - при "noop" ничего не трогаем, выравниваем seq и сразу ретрай
      if (data.status === "ok") {
        const accepted = Math.max(0, Math.min(amount, data.accepted_clicks | 0));

        // уменьшаем буфер только на реально принятые клики
        if (accepted > 0) {
          setBuffered((v) => Math.max(0, v - accepted));
        }

        // серверный seq — источник истины
        const srv = Number(data.server_seq ?? seq);
        if (!Number.isNaN(srv) && srv >= seqRef.current) {
          seqRef.current = srv;
        } else {
          seqRef.current = seq; // fallback
        }

        currentBatch.current = null;
        inflight.current = false;

        onReconcile(data);

        // если сервер принял меньше, остаток останется в буфере => пульнём следующий батч
        if (accepted < amount || buffered > 0) {
          scheduleRetry(0);
        }
      } else if (data.status === "noop") {
        // НИЧЕГО не списываем из буфера, НЕ трогаем текущий батч —
        // переинициализируем seq и повторяем ту же попытку
        const srv = Number(data.server_seq ?? 0);
        if (!Number.isNaN(srv) && srv >= seqRef.current) {
          seqRef.current = srv;
        }

        inflight.current = false;
        // не сбрасываем currentBatch: повторим её же, но с новым seq
        currentBatch.current = { seq: seqRef.current + 1, amount };

        scheduleRetry(50);
      } else {
        // статус error — мягкий ретрай без потери буфера
        inflight.current = false;
        scheduleRetry(300);
      }
    } catch {
      inflight.current = false;
      scheduleRetry(400);
    }
  };

  useEffect(() => {
    if (!enabled) return;
    const t = window.setInterval(() => {
      if (!inflight.current && buffered > 0) void flush();
    }, flushEveryMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flushEveryMs, buffered, enabled]);

  useEffect(() => {
    if (!enabled) return;
    if (buffered >= threshold && !inflight.current && !currentBatch.current) {
      void flush();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buffered, threshold, enabled]);

  useEffect(() => {
    if (!enabled) return;

    const handler = () => {
      if (buffered <= 0) return;

      // чтобы не ломать порядок — не шлём beacon, если есть инфлайт
      if (inflight.current) return;

      const rawInit = resolveInitData();
      if (!rawInit || !sessionId) return;

      const amount = Math.max(1, Math.min(buffered, maxBatch));
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
        // ВАЖНО: тут НИЧЕГО НЕ уменьшаем локально.
        // Дождёмся ответа через обычный fetch-поток при повторном запуске приложения.
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
  }, [buffered, sessionId, maxBatch, initData, enabled]);

  const forceFlush = () => { void flush(); };

  return { addClicks, forceFlush, buffered, lastSeq: seqRef.current };
}






