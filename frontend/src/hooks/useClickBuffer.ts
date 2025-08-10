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
  initData?: string;              // Telegram WebApp.initData
  sessionId: string;
  onReconcile: (r: FlushResponse) => void;
  flushEveryMs?: number;
  threshold?: number;
  initialSeq?: number;            // last_client_seq с бэка
  maxBatch?: number;              // = MAX_DELTA_PER_FLUSH на бэке
  enabled?: boolean;              // запуск флаша только после sync seq
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

  const bufferedRef = useRef(0);
  const inflight = useRef(false);
  const lastSeqRef = useRef<number>(initialSeq);
  const retryTimer = useRef<number | null>(null);

  // если initialSeq обновился после запроса прогресса — подтягиваем его
  useEffect(() => {
    if (typeof initialSeq === "number" && initialSeq > lastSeqRef.current) {
      lastSeqRef.current = initialSeq;
    }
  }, [initialSeq]);

  const setBufferedSafe = (n: number) => {
    bufferedRef.current = n;
    setBuffered(n);
  };

  const incBuffered = (n: number) => {
    if (n <= 0) return;
    setBufferedSafe(bufferedRef.current + n);
  };

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

  const drain = async () => {
    if (!enabled) return;
    if (inflight.current) return;

    // цикл — пока что-то накоплено, шлём пачками
    while (enabled && !inflight.current && bufferedRef.current > 0) {
      inflight.current = true;

      // сколько прямо сейчас отправим
      const toSend = Math.min(bufferedRef.current, maxBatch);
      const nextSeq = lastSeqRef.current + 1;

      try {
        const data = await postBatch(nextSeq, toSend);

        // критично: уменьшаем буфер только на принятые клики!
        const accepted = Math.max(0, data.accepted_clicks | 0);
        if (accepted > 0) {
          setBufferedSafe(Math.max(0, bufferedRef.current - accepted));
        }

        // синхронизируем seq с сервером, а не с отправленным значением
        lastSeqRef.current = Math.max(lastSeqRef.current, data.server_seq | 0);

        inflight.current = false;

        // позволяем родителю подтянуть авторитетное состояние
        onReconcile(data);

        // если ещё есть что слать — продолжим цикл сразу
        // (без setTimeout — но дадим JS очереди отработать)
        if (bufferedRef.current === 0) break;
      } catch {
        inflight.current = false;
        // бэкофф и повтор
        if (retryTimer.current) window.clearTimeout(retryTimer.current);
        retryTimer.current = window.setTimeout(() => {
          void drain();
        }, 400) as unknown as number;
        break; // выходим из цикла до ретрая
      }
    }
  };

  const addClicks = (n = 1) => {
    if (n <= 0) return;
    incBuffered(n);
    // если навалили много — стартуем дрен немедленно
    if (enabled && !inflight.current && bufferedRef.current >= threshold) {
      void drain();
    }
  };

  // авто-дрен по таймеру
  useEffect(() => {
    if (!enabled) return;
    const t = window.setInterval(() => {
      if (!inflight.current && bufferedRef.current > 0) void drain();
    }, flushEveryMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, flushEveryMs]);

  // «видимость»/закрытие — пытаемся отправить хотя бы одну пачку
  useEffect(() => {
    if (!enabled) return;

    const handler = () => {
      if (bufferedRef.current <= 0) return;
      const rawInit = resolveInitData();
      if (!rawInit || !sessionId) return;

      const amount = Math.max(1, Math.min(bufferedRef.current, maxBatch));
      const beacon = {
        init_data: rawInit,
        delta_clicks: amount,
        client_seq: lastSeqRef.current + 1,
        session_id: sessionId,
      };
      try {
        navigator.sendBeacon(
          `${API_BASE_URL}/api/game/clicks/flush`,
          new Blob([JSON.stringify(beacon)], { type: "application/json" })
        );
        // не списываем локально — дождёмся следующего /progress или ответа
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, sessionId, maxBatch, initData]);

  const forceFlush = () => void drain();

  return {
    addClicks,
    forceFlush,
    buffered,
    lastSeq: lastSeqRef.current,
    nextSeq: lastSeqRef.current + 1,
  };
}




