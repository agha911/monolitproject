import React from 'react';

interface MainButtonProps {
  onMultiClick: (x: number, y: number) => void;
  energy: number;
}

const MainButton: React.FC<MainButtonProps> = ({ onMultiClick, energy }) => {
  const handlePointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (energy <= 0) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const xPercent = ((e.clientX - rect.left) / rect.width) * 100;
    const yPercent = ((e.clientY - rect.top) / rect.height) * 100;

    onMultiClick(xPercent, yPercent);
  };

  return (
    <button
      onPointerDown={handlePointerDown}
      disabled={energy <= 0}
      className={`w-72 h-72 rounded-full overflow-hidden border-4 transition-transform duration-150 ease-out
        active:scale-95
        ${
          energy > 0
            ? 'border-[#00f0ff] bg-[#0e1a2b] shadow-[0_0_25px_#00f0ff]'
            : 'border-gray-500 bg-[#1a1a1a] opacity-50 cursor-not-allowed'
        }
      `}
    >
      <img
        src="./logo.png"
        alt="Main Coin"
        className="w-full h-full object-cover"
        draggable={false}
      />
    </button>
  );
};

export default MainButton;
















