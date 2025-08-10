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
  initData?: string;        // Telegram WebApp.initData
  sessionId: string;
  onReconcile: (r: FlushResponse) => void;
  flushEveryMs?: number;    // страховочный таймер
  threshold?: number;       // порог мгновенного старта
  initialSeq?: number;      // last_client_seq с бэка
  maxBatch?: number;        // = MAX_DELTA_PER_FLUSH на бэке
  maxBurst?: number;        // сколько батчей максимум за один дрейн-проход
};

export function useClickBuffer({
  initData,
  sessionId,
  onReconcile,
  flushEveryMs = 250,
  threshold = 20,
  initialSeq = 0,
  maxBatch = 50,
  maxBurst = 8,
}: Options) {
  // видимое состояние для UI
  const [buffered, setBuffered] = useState(0);
  // истинное значение буфера для синхронного чтения
  const bufferedRef = useRef(0);

  // сеттеры, которые поддерживают и state, и ref
  const incBuffered = (n: number) => {
    if (n <= 0) return;
    bufferedRef.current += n;
    setBuffered((v) => v + n);
  };
  const decBuffered = (n: number) => {
    if (n <= 0) return;
    const next = Math.max(0, bufferedRef.current - n);
    bufferedRef.current = next;
    setBuffered(next);
  };
  const setBufferedExact = (n: number) => {
    bufferedRef.current = Math.max(0, n);
    setBuffered(bufferedRef.current);
  };

  const inflight = useRef(false);
  const seqRef = useRef<number>(initialSeq);
  const retryTimer = useRef<number | null>(null);

  // подтягиваем seq, если пришёл новее
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
    incBuffered(n);
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

  /**
   * Дрейним буфер последовательно (без ожидания таймера).
   * Используем bufferedRef для синхронного чтения текущего размера.
   */
  const drain = async () => {
    if (inflight.current) return;
    inflight.current = true;

    try {
      let burst = maxBurst;

      while (burst-- > 0) {
        const toSend = Math.min(bufferedRef.current, maxBatch);
        if (toSend <= 0) break;

        const nextSeq = seqRef.current + 1;
        const data = await postBatch(nextSeq, toSend);

        const accepted = Math.max(0, data.accepted_clicks ?? 0);
        if (accepted > 0) {
          decBuffered(accepted);
        }

        // авторитетно обновляем seq
        if (typeof data.server_seq === "number" && data.server_seq >= seqRef.current) {
          seqRef.current = data.server_seq;
        } else {
          // fallback, чтобы не застревать
          seqRef.current = nextSeq;
        }

        onReconcile(data);

        // если сервер принял меньше, чем отправили — энергии не хватило
        if (accepted < toSend) {
          break;
        }
        // иначе — продолжаем без задержки, пока буфер не опустеет
      }
    } catch {
      if (retryTimer.current) window.clearTimeout(retryTimer.current);
      retryTimer.current = window.setTimeout(() => {
        void drain();
      }, 400) as unknown as number;
    } finally {
      inflight.current = false;
    }
  };

  // страховочный таймер
  useEffect(() => {
    const t = window.setInterval(() => {
      if (!inflight.current && bufferedRef.current > 0) void drain();
    }, flushEveryMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flushEveryMs]);

  // мгновенный старт при достижении порога
  useEffect(() => {
    if (buffered >= threshold && !inflight.current) {
      void drain();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buffered, threshold]);

  // best-effort при скрытии/закрытии вкладки
  useEffect(() => {
    const handler = () => {
      const pending = bufferedRef.current;
      if (pending <= 0) return;

      const rawInit = resolveInitData();
      if (!rawInit || !sessionId) return;

      const beaconAmount = Math.max(1, Math.min(pending, maxBatch));
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
        // локально спишем отправленное — остальное догрузит таймер после возврата
        decBuffered(beaconAmount);
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
  }, [sessionId, maxBatch, initData]);

  const forceFlush = () => drain();

  return { addClicks, forceFlush, buffered, lastSeq: seqRef.current, setBufferedExact };
}


