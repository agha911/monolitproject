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
  lockKey?: string;
  seqStorageKey?: string;
  /** стоп-кран: можно мгновенно запретить отправки (например при energy<=0) */
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
  canSend = true,
}: Options) {
  const [buffered, setBuffered] = useState(0);

  const inflight = useRef(false);
  const seqRef = useRef<number>(initialSeq);
  const currentBatch = useRef<{ seq: number; amount: number } | null>(null);
  const retryTimer = useRef<number | null>(null);
  const destroyedRef = useRef(false);

  const enabledRef = useRef(enabled);
  const canSendRef = useRef(canSend);
  useEffect(() => { enabledRef.current = enabled; }, [enabled]);
  useEffect(() => { canSendRef.current = canSend; }, [canSend]);

  // Счётчик добавленных кликов и «последней попытки».
  // Если попытка закончилась без приёма (accepted=0), мы не ретраим,
  // пока не появятся НОВЫЕ клики (addedTotal > lastTriedAdded).
  const addedTotalRef = useRef(0);
  const lastTriedAddedRef = useRef(0);

  useEffect(() => {
    if (typeof initialSeq === "number" && initialSeq > seqRef.current) {
      seqRef.current = initialSeq;
    }
  }, [initialSeq]);

  useEffect(() => {
    if (!seqStorageKey) return;
    const onStorage = (e: StorageEvent) => {
      if (e.key !== seqStorageKey) return;
      const n = Number(e.newValue ?? "0");
      if (!Number.isNaN(n) && n > seqRef.current) seqRef.current = n;
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [seqStorageKey]);

  const saveSeq = (n: number) => {
    try { if (seqStorageKey) localStorage.setItem(seqStorageKey, String(n)); } catch {}
  };

  const resolveInitData = () => {
    if (initData && initData.length > 0) return initData;
    const raw = (window as any)?.Telegram?.WebApp?.initData;
    return typeof raw === "string" ? raw : "";
  };

  const addClicks = (n = 1) => {
    if (n <= 0) return;
    addedTotalRef.current += n;         // отметим, что появились новые клики
    setBuffered((v) => v + n);
  };

  const postBatch = async (seq: number, amount: number) => {
    const safeSeq = Math.max(1, Math.floor(seq));
    const safeAmount = Math.min(Math.max(1, Math.floor(amount)), maxBatch);
    const rawInit = resolveInitData();
    if (!rawInit || !sessionId) throw new Error("flush blocked: missing init_data or session_id");

    const resp = await fetch(`${API_BASE_URL}/api/game/clicks/flush`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        init_data: rawInit,
        delta_clicks: safeAmount,
        client_seq: safeSeq,
        session_id: sessionId,
      }),
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
    retryTimer.current = window.setTimeout(() => { void flush(); }, ms) as unknown as number;
  };

  const withLock = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    const locks = (navigator as any).locks;
    if (!lockKey || !locks?.request) return fn();
    return locks.request(
      `gappick:flush:${lockKey}`,
      { mode: "exclusive", ifAvailable: true },
      async (lock: any) => (!lock ? undefined : fn())
    );
  };

  const flushCore = async () => {
    if (destroyedRef.current) return;
    if (!enabledRef.current || !canSendRef.current) return;
    if (inflight.current) return;

    // если прошлую попытку ничего не приняли, ждём новых кликов
    if (buffered > 0 && addedTotalRef.current <= lastTriedAddedRef.current) return;

    if (!currentBatch.current) {
      if (buffered <= 0) return;
      currentBatch.current = {
        seq: seqRef.current + 1,
        amount: Math.min(buffered, maxBatch),
      };
    }

    const { seq, amount } = currentBatch.current;
    inflight.current = true;

    // фиксируем «на каком количестве добавленных кликов мы пробовали»
    const snapshotAdded = addedTotalRef.current;

    try {
      const data = await postBatch(seq, amount);

      const srv = Number(data.server_seq ?? 0);
      if (!Number.isNaN(srv) && srv >= seqRef.current) {
        seqRef.current = srv;
        saveSeq(srv);
      }

      const accepted = Math.max(0, Math.min(amount, data.accepted_clicks | 0));

      if (data.status === "ok" && accepted > 0) {
        setBuffered((v) => Math.max(0, v - accepted));
        lastTriedAddedRef.current = snapshotAdded; // попытка удачная
        inflight.current = false;
        currentBatch.current = null;

        try { onReconcile(data); } catch {}

        if (buffered > 0 && canSendRef.current) scheduleRetry(0); // продолжаем дожёвывать
      } else {
        // noop/ошибка или ok с 0 принятых — НЕ ретраим автоматически
        // до появления новых кликов
        lastTriedAddedRef.current = snapshotAdded;
        inflight.current = false;
        currentBatch.current = null;
        // onReconcile всё равно дернём — пусть UI синхронизируется
        try { onReconcile(data); } catch {}
      }
    } catch {
      // сеть/исключение — тоже ждём новых кликов
      lastTriedAddedRef.current = snapshotAdded;
      inflight.current = false;
      currentBatch.current = null;
    }
  };

  const flush = async () => {
    if (!enabledRef.current || !canSendRef.current) return;
    await withLock(flushCore);
  };

  // периодический флеш — только если есть новые клики с момента последней неуспешной попытки
  useEffect(() => {
    if (!enabled) return;
    const t = window.setInterval(() => {
      if (!inflight.current &&
          buffered > 0 &&
          canSendRef.current &&
          addedTotalRef.current > lastTriedAddedRef.current) {
        void flush();
      }
    }, flushEveryMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flushEveryMs, buffered, enabled, canSend]);

  // пороговый триггер
  useEffect(() => {
    if (!enabled || !canSend) return;
    if (buffered >= threshold &&
        !inflight.current &&
        !currentBatch.current &&
        addedTotalRef.current > lastTriedAddedRef.current) {
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











