// frontend/src/hooks/useClickBuffer.ts
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
  enabled?: boolean; // ← можно выключать флаш до синка seq
};

export function useClickBuffer({
  initData,
  sessionId,
  onReconcile,
  flushEveryMs = 200,
  threshold = 50,
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
    if (!enabled || inflight.current) return;

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

      const accepted = Math.max(0, Math.min(data.accepted_clicks ?? 0, amount));
      // КЛЮЧЕВОЕ: удаляем из буфера только ПРИНЯТЫЕ клики,
      // остальное оставляем (оно дольётся следующими флашами)
      setBuffered((v) => Math.max(0, v - accepted));

      // Выравниваем локальную последовательность по серверу,
      // а не по «попытке»
      if (Number.isFinite(data.server_seq)) {
        seqRef.current = data.server_seq;
      } else {
        // на всякий случай
        seqRef.current = Math.max(seqRef.current, seq);
      }

      currentBatch.current = null;
      inflight.current = false;

      onReconcile(data);
    } catch (e) {
      inflight.current = false;
      // не трогаем буфер, просто повторим попытку
      if (retryTimer.current) window.clearTimeout(retryTimer.current);
      retryTimer.current = window.setTimeout(() => {
        void flush();
      }, 300) as unknown as number;
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

  // best-effort отправка при закрытии вкладки
  useEffect(() => {
    if (!enabled) return;
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
  }, [buffered, sessionId, maxBatch, initData, enabled]);

  const forceFlush = () => void flush();

  return { addClicks, forceFlush, buffered, lastSeq: seqRef.current };
}






