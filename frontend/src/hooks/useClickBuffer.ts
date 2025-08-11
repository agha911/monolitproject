import { useEffect, useMemo, useRef, useState } from "react";
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
  enabled?: boolean; // внешнее включение/выключение
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

  // флаги-предохранители
  const [isMaster, setIsMaster] = useState(true);
  const enabledLocal = enabled && isMaster;

  const inflight = useRef(false);
  const seqRef = useRef<number>(initialSeq);
  const currentBatch = useRef<{ seq: number; amount: number } | null>(null);
  const retryTimer = useRef<number | null>(null);

  // подхватываем initialSeq, если он вырос (после /progress)
  useEffect(() => {
    if (typeof initialSeq === "number" && initialSeq > seqRef.current) {
      seqRef.current = initialSeq;
    }
  }, [initialSeq]);

  // единый «мастер»-флашер на вкладку (страховка от двойного монтирования)
  useEffect(() => {
    const k = "__GAPPICK_FLUSH_MASTER__";
    if (!(window as any)[k]) {
      (window as any)[k] = true;
      setIsMaster(true);
      return () => {
        delete (window as any)[k];
      };
    } else {
      setIsMaster(false);
      return;
    }
  }, []);

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

  const scheduleRetry = (ms = 120) => {
    if (retryTimer.current) window.clearTimeout(retryTimer.current);
    retryTimer.current = window.setTimeout(() => {
      void runWithLock(flush);
    }, ms) as unknown as number;
  };

  // если есть Web Locks — используем для взаимоисключения даже между вкладками
  const runWithLock = async (fn: () => Promise<void>) => {
    const locks = (navigator as any)?.locks;
    if (locks?.request) {
      await locks.request("gappick-flush", { mode: "exclusive" }, fn);
    } else {
      await fn();
    }
  };

  const flush = async () => {
    if (!enabledLocal) return;
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

      if (data.status === "ok") {
        const accepted = Math.max(0, Math.min(amount, data.accepted_clicks | 0));

        if (accepted > 0) {
          setBuffered((v) => Math.max(0, v - accepted));
        }

        const srv = Number(data.server_seq ?? seq);
        if (!Number.isNaN(srv) && srv >= seqRef.current) {
          seqRef.current = srv;
        } else {
          seqRef.current = seq;
        }

        currentBatch.current = null;
        inflight.current = false;

        onReconcile(data);

        // если что-то осталось — отправим следующую пачку
        if (accepted < amount || buffered > 0) {
          scheduleRetry(0);
        }
      } else if (data.status === "noop") {
        // не трогаем буфер, поднимаем seq и повторяем ту же пачку
        const srv = Number(data.server_seq ?? 0);
        if (!Number.isNaN(srv) && srv >= seqRef.current) {
          seqRef.current = srv;
        }
        inflight.current = false;
        currentBatch.current = { seq: seqRef.current + 1, amount };
        scheduleRetry(50);
      } else {
        // error — мягкий ретрай
        inflight.current = false;
        scheduleRetry(300);
      }
    } catch {
      inflight.current = false;
      scheduleRetry(400);
    }
  };

  // периодический флаш
  useEffect(() => {
    if (!enabledLocal) return;
    const t = window.setInterval(() => {
      if (!inflight.current && buffered > 0) void runWithLock(flush);
    }, flushEveryMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flushEveryMs, buffered, enabledLocal]);

  // триггер при пороге
  useEffect(() => {
    if (!enabledLocal) return;
    if (buffered >= threshold && !inflight.current && !currentBatch.current) {
      void runWithLock(flush);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buffered, threshold, enabledLocal]);

  // best-effort отправка при закрытии вкладки
  useEffect(() => {
    if (!enabledLocal) return;

    const handler = () => {
      if (buffered <= 0) return;
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
  }, [buffered, sessionId, maxBatch, initData, enabledLocal]);

  const forceFlush = () => {
    void runWithLock(flush);
  };

  return { addClicks, forceFlush, buffered, lastSeq: seqRef.current };
}








