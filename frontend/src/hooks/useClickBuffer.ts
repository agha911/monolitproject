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
  initData?: string;
  sessionId: string;
  onReconcile: (r: FlushResponse) => void;
  flushEveryMs?: number;
  threshold?: number;
  initialSeq?: number;   // last_client_seq c бэка
  maxBatch?: number;     // = MAX_DELTA_PER_FLUSH
  maxBurst?: number;     // батчей за один проход
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
  const [buffered, setBuffered] = useState(0);
  const bufferedRef = useRef(0);

  const inflight = useRef(false);

  // last подтверждённый seq с сервера
  const lastSeqRef = useRef<number>(initialSeq);
  // nextSeqRef — номер, который БУДЕТ отправлен в следующем запросе
  const nextSeqRef = useRef<number>(initialSeq + 1);

  const retryTimer = useRef<number | null>(null);

  // если initialSeq подтянули позже — синхронизируем оба рефа
  useEffect(() => {
    if (typeof initialSeq === "number" && initialSeq > lastSeqRef.current) {
      lastSeqRef.current = initialSeq;
      nextSeqRef.current = initialSeq + 1;
    }
  }, [initialSeq]);

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

  const resolveInitData = () => {
    if (initData && initData.length > 0) return initData;
    const w = (typeof window !== "undefined" ? (window as any) : undefined);
    const raw = w?.Telegram?.WebApp?.initData;
    return typeof raw === "string" && raw.length > 0 ? raw : "";
  };

  const addClicks = (n = 1) => incBuffered(n);

  const postBatch = async (seq: number, amount: number) => {
    const rawInit = resolveInitData();
    if (!rawInit || !sessionId) throw new Error("flush blocked: no init_data or session_id");
    const payload = {
      init_data: rawInit,
      delta_clicks: Math.max(1, Math.min(Math.floor(amount), maxBatch)),
      client_seq: Math.max(1, Math.floor(seq)),
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

  // ДРЕЙН: резервируем seq ДО отправки и используем его и при ретраях.
  const drain = async () => {
    if (inflight.current) return;
    inflight.current = true;
    try {
      let burst = maxBurst;

      while (burst-- > 0) {
        const toSend = Math.min(bufferedRef.current, maxBatch);
        if (toSend <= 0) break;

        // РЕЗЕРВ: берём текущий nextSeq и не трогаем его до ответа
        const useSeq = nextSeqRef.current;

        let data: FlushResponse;
        try {
          data = await postBatch(useSeq, toSend);
        } catch (e) {
          // при ошибке повторим ТОТ ЖЕ seq позже
          if (retryTimer.current) window.clearTimeout(retryTimer.current);
          retryTimer.current = window.setTimeout(() => void drain(), 400) as unknown as number;
          break;
        }

        const accepted = Math.max(0, data.accepted_clicks ?? 0);
        if (accepted > 0) decBuffered(accepted);

        // сервер подтвердил seq -> продвигаем last и next
        // (учитываем случай, когда сервер мог “догнать/перепрыгнуть”)
        const serverSeq = Number(data.server_seq ?? 0);
        if (serverSeq >= lastSeqRef.current) {
          lastSeqRef.current = serverSeq;
          nextSeqRef.current = serverSeq + 1;
        } else {
          // fallback, чтобы не застрять
          lastSeqRef.current = useSeq;
          nextSeqRef.current = useSeq + 1;
        }

        onReconcile(data);

        // если энергии не хватило (приняли меньше, чем отправили) — ждём восстановления
        if (accepted < toSend) break;
      }
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
  }, [flushEveryMs]);

  // мгновенный старт при достижении порога
  useEffect(() => {
    if (buffered >= threshold && !inflight.current) void drain();
  }, [buffered, threshold]);

  // best-effort на закрытие/сворачивание
  useEffect(() => {
    const handler = () => {
      const pending = bufferedRef.current;
      if (pending <= 0) return;
      const rawInit = resolveInitData();
      if (!rawInit || !sessionId) return;

      const amount = Math.max(1, Math.min(pending, maxBatch));
      const beacon = {
        init_data: rawInit,
        delta_clicks: amount,
        // используем текущий nextSeq (а не last+1 “на глаз”)
        client_seq: nextSeqRef.current,
        session_id: sessionId,
      };
      try {
        navigator.sendBeacon(
          `${API_BASE_URL}/api/game/clicks/flush`,
          new Blob([JSON.stringify(beacon)], { type: "application/json" })
        );
        // локально спишем только отправленное
        decBuffered(amount);
        // и сдвинем next — beacon мы уже заняли
        lastSeqRef.current = Math.max(lastSeqRef.current, nextSeqRef.current);
        nextSeqRef.current = lastSeqRef.current + 1;
      } catch {}
    };
    const vis = () => document.visibilityState === "hidden" && handler();

    window.addEventListener("beforeunload", handler);
    document.addEventListener("visibilitychange", vis);
    return () => {
      window.removeEventListener("beforeunload", handler);
      document.removeEventListener("visibilitychange", vis);
    };
  }, [sessionId, maxBatch, initData]);

  const forceFlush = () => void drain();

  return {
    addClicks,
    forceFlush,
    buffered,
    // для дебага можно логировать это в UI
    lastSeq: lastSeqRef.current,
    nextSeq: nextSeqRef.current,
  };
}


