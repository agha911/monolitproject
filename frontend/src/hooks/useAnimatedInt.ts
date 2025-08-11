import { useEffect, useRef, useState } from "react";

type Options = {
  /** миллисекунд на 1 единицу дельты (чем больше — тем медленнее) */
  speedPerUnit?: number;
  /** минимальная длительность анимации, мс */
  minDuration?: number;
  /** максимальная длительность анимации, мс */
  maxDuration?: number;
};

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));

/**
 * Сглаживает целевое число target. ВАЖНО: новая анимация
 * всегда стартует от текущего визуального значения.
 */
export function useAnimatedInt(target: number, opts: Options = {}) {
  const {
    speedPerUnit = 8,
    minDuration = 120,
    maxDuration = 600,
  } = opts;

  // Визуальное значение
  const [value, setValue] = useState<number>(target);

  // Рефы для стабильной анимации
  const rafId = useRef<number | null>(null);
  const startTsRef = useRef<number>(0);
  const fromRef = useRef<number>(target);
  const toRef = useRef<number>(target);
  const durRef = useRef<number>(0);
  const valueRef = useRef<number>(target); // текущее отрисованное (источник правды для рестартов)

  // синхронизация ref со state
  useEffect(() => {
    valueRef.current = value;
  }, [value]);

  useEffect(() => {
    // если цель не менялась — ничего не делаем
    if (toRef.current === target) return;

    // стартуем НОВУЮ анимацию от текущего визуального значения
    const from = valueRef.current;
    const to = target;
    fromRef.current = from;
    toRef.current = to;

    const distance = Math.abs(to - from);
    const duration = clamp(distance * speedPerUnit, minDuration, maxDuration);
    durRef.current = duration;
    startTsRef.current = 0;

    if (rafId.current) cancelAnimationFrame(rafId.current);

    const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

    const step = (ts: number) => {
      if (!startTsRef.current) startTsRef.current = ts;
      const t = durRef.current > 0 ? clamp((ts - startTsRef.current) / durRef.current, 0, 1) : 1;

      const curFrom = fromRef.current;
      const curTo = toRef.current;
      const next = curFrom + (curTo - curFrom) * easeOutCubic(t);

      setValue(next);

      // если цель не достигли и цель не поменялась — продолжаем
      if (t < 1 && toRef.current === curTo) {
        rafId.current = requestAnimationFrame(step);
      } else {
        // защёлкиваемся точно в цель
        setValue(toRef.current);
        valueRef.current = toRef.current;
        fromRef.current = toRef.current;
        rafId.current = null;
      }
    };

    rafId.current = requestAnimationFrame(step);

    return () => {
      if (rafId.current) cancelAnimationFrame(rafId.current);
      rafId.current = null;
    };
  }, [target, speedPerUnit, minDuration, maxDuration]);

  // на самом первом рендере не дёргаем — уже инициализировали state таргетом
  return value;
}
