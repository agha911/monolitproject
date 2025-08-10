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

  /**
   * Дрейним буфер последовательно, без ожидания таймера:
   * шлём батчи, пока сервер принимает >= того, что мы отправили,
   * и пока есть что отправлять.
   */
  const drain = async () => {
    if (inflight.current) return;
    inflight.current = true;

    try {
      // ограничитель на количество последовательных запросов за один проход,
      // чтобы не забивать сеть при огромном буфере
      let safety = 8;

      while (safety > 0) {
        safety--;

        let toSend = 0;
        // захватываем текущий размер буфера атомарно
        setBuffered((v) => {
          toSend = Math.min(v, maxBatch);
          return v; // не меняем здесь — изменим после ответа
        });

        if (toSend <= 0) break;

        const nextSeq = seqRef.current + 1;
        const data = await postBatch(nextSeq, toSend);

        const accepted = Math.max(0, data.accepted_clicks ?? 0);

        // уменьшаем буфер ровно на принятую часть
        if (accepted > 0) {
          setBuffered((v) => Math.max(0, v - accepted));
        }

        // фиксируем seq по серверу
        if (typeof data.server_seq === "number" && data.server_seq >= seqRef.current) {
          seqRef.current = data.server_seq;
        } else {
          // на всякий — чтобы не застревать
          seqRef.current = nextSeq;
        }

        onReconcile(data);

        // если сервер принял меньше, чем отправили — энергии нет,
        // останавливаемся до следующего таймера/восстановления энергии
        if (accepted < Math.min(toSend, maxBatch)) {
          break;
        }

        // если буфер ещё есть — крутим цикл дальше (без задержки)
      }
    } catch {
      // мягкий бэкофф и повтор
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
      if (!inflight.current && buffered > 0) void drain();
    }, flushEveryMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flushEveryMs, buffered]);

  // мгновенный старт при достижении порога
  useEffect(() => {
    if (buffered >= threshold && !inflight.current) {
      void drain();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buffered, threshold]);

  // best-effort при скрытии/закрытии вкладки (один батч)
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

  const forceFlush = () => drain();

  return { addClicks, forceFlush, buffered, lastSeq: seqRef.current };
}

