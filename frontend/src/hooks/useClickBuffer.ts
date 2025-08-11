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
  enabled?: boolean;
  /** общий ключ блокировки между вкладками (передавайте userId) */
  lockKey?: string;
  /** ключ localStorage для хранения lastSeq (передаёте тот, что уже есть у вас) */
  seqStorageKey?: string;
  /** НОВОЕ: можно мгновенно заглушить отправки (например, при energy<=0) */
  canSend?: boolean;
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
  lockKey,
  seqStorageKey,
  canSend = true, // NEW
}: Options) {
  const [buffered, setBuffered] = useState(0);

  const inflight = useRef(false);
  const seqRef = useRef<number>(initialSeq);
  const currentBatch = useRef<{ seq: number; amount: number } | null>(null);
  const retryTimer = useRef<number | null>(null);
  const enabledRef = useRef(enabled);
  const canSendRef = useRef(canSend);
  const destroyedRef = useRef(false);

  useEffect(() => { enabledRef.current = enabled; }, [enabled]);
  useEffect(() => { canSendRef.current = canSend; }, [canSend]);

  // подтягиваем initialSeq (если вдруг на старте пришёл более свежий)
  useEffect(() => {
    if (typeof initialSeq === "number" && initialSeq > seqRef.current) {
      seqRef.current = initialSeq;
    }
  }, [initialSeq]);

  // кросс-вкладочная синхронизация lastSeq через localStorage
  useEffect(() => {
    if (!seqStorageKey) return;
    const onStorage = (e: StorageEvent) => {
      if (e.key !== seqStorageKey) return;
      const n = Number(e.newValue ?? "0");
      if (!Number.isNaN(n) && n > seqRef.current) {
        seqRef.current = n;
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [seqStorageKey]);

  // helper: сохраняем seq в localStorage как «истину» для других вкладок
  const saveSeq = (n: number) => {
    try {
      if (seqStorageKey) localStorage.setItem(seqStorageKey, String(n));
    } catch {}
  };

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
    const safeAmount = Math.min(Math.floor(amount), maxBatch);
    if (safeAmount <= 0) {
      throw new Error("flush blocked: empty amount");
    }
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
    if (!enabledRef.current || !canSendRef.current) return;
    retryTimer.current = window.setTimeout(() => {
      void flush();
    }, ms) as unknown as number;
  };

  // универсальный раннер с Web Locks (серилизация между вкладками)
  const withLock = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    const locks = (navigator as any).locks;
    if (!lockKey || !locks || !locks.request) {
      return fn();
    }
    return locks.request(
      `gappick:flush:${lockKey}`,
      { mode: "exclusive", ifAvailable: true },
      async (lock: any) => {
        if (!lock) {
          scheduleRetry(50);
          return undefined;
        }
        return fn();
      }
    );
  };

  const flushCore = async () => {
    if (destroyedRef.current) return;
    if (!enabledRef.current) return;
    if (!canSendRef.current) return;
    if (inflight.current) return;

    if (!currentBatch.current) {
      if (buffered <= 0) return; // не создаём батч при пустом буфере
      currentBatch.current = {
        seq: seqRef.current + 1,
        amount: Math.min(buffered, maxBatch), // ровно min(buffered, maxBatch)
      };
    }

    const { seq, amount } = currentBatch.current;
    inflight.current = true;

    try {
      const data = await postBatch(seq, amount);

      // выравниваем seq по серверу в любом случае, если прислал
      const srv = Number(data.server_seq ?? 0);
      if (!Number.isNaN(srv) && srv >= seqRef.current) {
        seqRef.current = srv;
        saveSeq(srv);
      }

      if (data.status === "ok") {
        const accepted = Math.max(0, Math.min(amount, data.accepted_clicks | 0));
        setBuffered((v) => Math.max(0, v - accepted));

        inflight.current = false;
        currentBatch.current = null;

        // наружный reconcile
        try { onReconcile(data); } catch {}

        // если ещё есть буфер — продолжим
        if (buffered > 0 && canSendRef.current) {
          scheduleRetry(0);
        }
      } else if (data.status === "noop") {
        // дубликат/старый — просто сбрасываем батч и пробуем заново ТОЛЬКО если есть буфер
        inflight.current = false;
        currentBatch.current = null;
        if (buffered > 0 && canSendRef.current) {
          scheduleRetry(60);
        }
      } else {
        // ошибка со стороны сервера (но HTTP 200) — отпускаем и ретраим, если есть смысл
        inflight.current = false;
        currentBatch.current = null;
        if (buffered > 0 && canSendRef.current) {
          scheduleRetry(300);
        }
      }
    } catch {
      inflight.current = false;
      currentBatch.current = null;
      if (buffered > 0 && canSendRef.current) {
        scheduleRetry(400);
      }
    }
  };

  const flush = async () => {
    if (!enabledRef.current) return;
    if (!canSendRef.current) return;
    await withLock(flushCore);
  };

  // периодический флешер — только если что-то в буфере
  useEffect(() => {
    if (!enabled) return;
    const t = window.setInterval(() => {
      if (!inflight.current && buffered > 0 && canSendRef.current) {
        void flush();
      }
    }, flushEveryMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flushEveryMs, buffered, enabled, canSend]);

  // пороговый триггер
  useEffect(() => {
    if (!enabled) return;
    if (!canSend) return;
    if (buffered >= threshold && !inflight.current && !currentBatch.current) {
      void flush();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buffered, threshold, enabled, canSend]);

  useEffect(() => {
    return () => {
      destroyedRef.current = true;
      if (retryTimer.current) window.clearTimeout(retryTimer.current);
    };
  }, []);

  const forceFlush = () => { void flush(); };

  return { addClicks, forceFlush, buffered, lastSeq: seqRef.current };
}










