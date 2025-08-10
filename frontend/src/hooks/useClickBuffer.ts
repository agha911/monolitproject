// frontend/src/hooks/useClickBuffer.ts
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
  initData?: string;              // Telegram WebApp.initData (может прийти из SDK)
  sessionId: string;
  onReconcile: (r: FlushResponse) => void;
  flushEveryMs?: number;
  threshold?: number;
  initialSeq?: number;            // ПОДАЁМ last_client_seq с бэка
  maxBatch?: number;              // = MAX_DELTA_PER_FLUSH на бэке
};

export function useClickBuffer({
  initData,
  sessionId,
  onReconcile,
  flushEveryMs = 250,
  threshold = 20,
  initialSeq = 0,
  maxBatch = 50,
}: Options) {
  const [buffered, setBuffered] = useState(0);

  const inflight = useRef(false);
  const seqRef = useRef<number>(initialSeq);
  const currentBatch = useRef<{ seq: number; amount: number } | null>(null);
  const retryTimer = useRef<number | null>(null);

  // если initialSeq обновился после запроса прогресса — подтягиваем его
  useEffect(() => {
    if (typeof initialSeq === "number" && initialSeq > seqRef.current) {
      seqRef.current = initialSeq;
    }
  }, [initialSeq]);

  const resolveInitData = () => {
    if (initData && initData.length > 0) return initData;
    if (typeof window !== "undefined") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

  const flush = async () => {
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

      // ↓↓↓ ВАЖНО: уменьшаем буфер только на ПРИНЯТЫЕ сервером клики
      const accepted = Math.max(0, data.accepted_clicks ?? 0);
      setBuffered((v) => Math.max(0, v - accepted));

      // обновляем локальный seq авторитетно ответом сервера
      seqRef.current = (data.server_seq ?? 0) > 0 ? data.server_seq : seq;

      currentBatch.current = null;
      inflight.current = false;

      onReconcile(data);
    } catch {
      inflight.current = false;
      // оставляем currentBatch.current как есть и пробуем повторить
      if (retryTimer.current) window.clearTimeout(retryTimer.current);
      retryTimer.current = window.setTimeout(() => {
        void flush();
      }, 400) as unknown as number;
    }
  };

  useEffect(() => {
    const t = window.setInterval(() => {
      if (!inflight.current && buffered > 0) void flush();
    }, flushEveryMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flushEveryMs, buffered]);

  useEffect(() => {
    if (buffered >= threshold && !inflight.current && !currentBatch.current) {
      void flush();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buffered, threshold]);

  useEffect(() => {
    const handler = () => {
      if (buffered <= 0) return;

      const rawInit = resolveInitData();
      if (!rawInit || !sessionId) return;

      const beaconAmount = Math.max(1, Math.min(buffered, maxBatch));
      const beacon = {
        init_data: rawInit,
        delta_clicks: beaconAmount,
        client_seq: seqRef.current + 1,
        session_id: sessionId,
      };
      try {
        navigator.sendBeacon(
          `${API_BASE_URL}/api/game/clicks/flush`,
          new Blob([JSON.stringify(beacon)], { type: "application/json" })
        );
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
  }, [buffered, sessionId, maxBatch, initData]);

  const forceFlush = () => flush();

  return { addClicks, forceFlush, buffered, lastSeq: seqRef.current };
}
