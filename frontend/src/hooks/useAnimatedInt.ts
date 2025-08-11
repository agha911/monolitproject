// frontend/src/hooks/useAnimatedInt.ts
import { useEffect, useRef, useState } from "react";

type Opts = {
  /** мс на 1 единицу изменения (динамическая длительность) */
  speedPerUnit?: number;
  /** максимум длительности анимации, мс */
  maxDuration?: number;
  /** минимум длительности анимации, мс */
  minDuration?: number;
  /** функция сглаживания 0..1 -> 0..1 */
  easing?: (t: number) => number;
};

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

export function useAnimatedInt(target: number, opts: Opts = {}) {
  const {
    speedPerUnit = 8,
    maxDuration = 600,
    minDuration = 120,
    easing = easeOutCubic,
  } = opts;

  const [value, setValue] = useState<number>(target);

  const raf = useRef<number | null>(null);
  const fromRef = useRef<number>(target);
  const toRef = useRef<number>(target);
  const startRef = useRef<number>(0);
  const durRef = useRef<number>(0);

  useEffect(() => {
    // отменим прошлую анимацию
    if (raf.current) cancelAnimationFrame(raf.current);

    const from = value;
    const to = Math.round(target);
    if (from === to) return;

    fromRef.current = from;
    toRef.current = to;

    const delta = Math.abs(to - from);
    const duration = Math.min(
      maxDuration,
      Math.max(minDuration, delta * speedPerUnit)
    );
    durRef.current = duration;
    startRef.current = performance.now();

    const tick = (now: number) => {
      const elapsed = now - startRef.current;
      const t = Math.max(0, Math.min(1, elapsed / durRef.current));
      const k = easing(t);
      const next = Math.round(fromRef.current + (toRef.current - fromRef.current) * k);
      if (next !== value) setValue(next);

      if (t < 1) {
        raf.current = requestAnimationFrame(tick);
      } else {
        // финальное прилипание к цели
        if (value !== toRef.current) setValue(toRef.current);
        raf.current = null;
      }
    };

    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
      raf.current = null;
    };
    // важно: зависим от target, но не от value (иначе зациклится)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, speedPerUnit, maxDuration, minDuration, easing]);

  return value;
}
