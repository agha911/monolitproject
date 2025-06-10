import React from 'react';

interface MainButtonProps {
  onHoldTick: () => void;
  energy: number;
}

const MainButton: React.FC<MainButtonProps> = ({ onHoldTick, energy }) => {
  return (
    <button
      onClick={onHoldTick}
      disabled={energy <= 0}
      className={`w-32 h-32 rounded-full overflow-hidden border-4 transition-all duration-200
        ${
          energy > 0
            ? 'border-[#00f0ff] bg-[#0e1a2b] hover:scale-105 animate-pulseNeon'
            : 'border-gray-500 bg-[#1a1a1a] opacity-50 cursor-not-allowed'
        }
      `}
    >
      <img
        src="/logo.png"
        alt="Main Coin"
        className="w-full h-full object-cover"
      />
    </button>
  );
};

export default MainButton;


