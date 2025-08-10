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
  initData: string;               // Telegram init_data (строка из WebApp)
  sessionId: string;
  onReconcile: (r: FlushResponse) => void; // применяем авторитетные значения от сервера
  flushEveryMs?: number;          // интервал авто-флаша
  threshold?: number;             // порог кликов для немедленного флаша
  initialSeq?: number;            // если хранишь seq в localStorage
};

export function useClickBuffer({
  initData,
  sessionId,
  onReconcile,
  flushEveryMs = 250,
  threshold = 20,
  initialSeq = 0,
}: Options) {
  const [buffered, setBuffered] = useState(0);

  // текущее состояние отправки
  const inflight = useRef(false);
  const seqRef = useRef<number>(initialSeq);
  const currentBatch = useRef<{ seq: number; amount: number } | null>(null);
  const retryTimer = useRef<number | null>(null);

  const addClicks = (n = 1) => {
    if (n <= 0) return;
    setBuffered((v) => v + n);
  };

  const postBatch = async (seq: number, amount: number) => {
    const resp = await fetch(`${API_BASE_URL}/api/game/clicks/flush`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        init_data: initData,        // ✅ соответствует ClicksFlushIn
        delta_clicks: amount,
        client_seq: seq,            // ≥ 1
        session_id: sessionId,
      }),
    });
    if (!resp.ok) throw new Error(`flush failed ${resp.status}`);
    const data: FlushResponse = await resp.json();
    return data;
  };

  const flush = async () => {
    if (inflight.current) return;

    // Если нет активного батча — сформируем его из текущего буфера
    if (!currentBatch.current) {
      if (buffered <= 0) return;
      currentBatch.current = {
        seq: seqRef.current + 1,
        amount: buffered,
      };
    }

    const { seq, amount } = currentBatch.current;
    inflight.current = true;

    try {
      const data = await postBatch(seq, amount);

      // Сервер принял — уменьшаем буфер ровно на отправленный батч
      setBuffered((v) => Math.max(0, v - amount));

      // Обновляем последний успешный seq
      seqRef.current = seq;

      // Обнуляем батч и снимаем флаг отправки
      currentBatch.current = null;
      inflight.current = false;

      onReconcile(data);
    } catch {
      // Не получилось — повторим тот же батч с тем же seq чуть позже
      inflight.current = false;
      if (retryTimer.current) window.clearTimeout(retryTimer.current);
      retryTimer.current = window.setTimeout(() => {
        void flush();
      }, 400) as unknown as number;
    }
  };

  // Авто-флаш по таймеру
  useEffect(() => {
    const t = window.setInterval(() => {
      if (!inflight.current && buffered > 0) void flush();
    }, flushEveryMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flushEveryMs, buffered]);

  // Немедленный флаш при достижении порога
  useEffect(() => {
    if (buffered >= threshold && !inflight.current && !currentBatch.current) {
      void flush();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buffered, threshold]);

  // Попытка сохранить клики при закрытии вкладки
  useEffect(() => {
    const handler = () => {
      if (buffered <= 0) return;
      const beacon = {
        init_data: initData,
        delta_clicks: buffered,
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
  }, [buffered, initData, sessionId]);

  const forceFlush = () => flush();

  return { addClicks, forceFlush, buffered, lastSeq: seqRef.current };
}

