import React, { useRef } from 'react';

interface MainButtonProps {
  onMultiClick: (x: number, y: number) => void;
  energy: number;
}

const MainButton: React.FC<MainButtonProps> = ({ onMultiClick, energy }) => {
  // Храним активные pointerId, чтобы не ловить дубликаты
  const activePointers = useRef<Set<number>>(new Set());

  const computeRelativePos = (e: React.PointerEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const xPercent = ((e.clientX - rect.left) / rect.width) * 100;
    const yPercent = ((e.clientY - rect.top) / rect.height) * 100;
    return { xPercent, yPercent };
  };

  const handlePointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (energy <= 0) return;

    // Отменяем жесты браузера (зум, скролл при тапе и т.п.)
    e.preventDefault();

    // Мультитач: каждый новый pointerId — отдельный клик
    const id = e.pointerId;
    if (activePointers.current.has(id)) return;
    activePointers.current.add(id);

    // Захватываем указатель, чтобы гарантированно получить up/cancel
    try {
      (e.currentTarget as any).setPointerCapture?.(id);
    } catch {
      /* ignore */
    }

    const { xPercent, yPercent } = computeRelativePos(e);
    onMultiClick(xPercent, yPercent);
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    activePointers.current.delete(e.pointerId);
    try {
      (e.currentTarget as any).releasePointerCapture?.(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  const handlePointerCancel = (e: React.PointerEvent<HTMLButtonElement>) => {
    activePointers.current.delete(e.pointerId);
    try {
      (e.currentTarget as any).releasePointerCapture?.(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    // Убираем системное меню при долгом тапе на мобильных
    e.preventDefault();
  };

  return (
    <button
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
      onContextMenu={handleContextMenu}
      disabled={energy <= 0}
      // отключаем браузерные жесты и выделение, чтобы мультитач был чище
      className={`w-72 h-72 rounded-full overflow-hidden border-4 transition-transform duration-150 ease-out
        touch-none select-none active:scale-95
        ${
          energy > 0
            ? 'border-[#00f0ff] bg-[#0e1a2b] shadow-[0_0_25px_#00f0ff]'
            : 'border-gray-500 bg-[#1a1a1a] opacity-50 cursor-not-allowed'
        }`}
    >
      <img
        src="./logo_2.jpg"
        alt="Main Coin"
        className="w-full h-full object-cover pointer-events-none select-none"
        draggable={false}
      />
    </button>
  );
};

export default MainButton;

















