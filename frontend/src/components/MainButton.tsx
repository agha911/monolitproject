import React, { useState } from 'react';

interface MainButtonProps {
  onHoldTick: () => void;
  energy: number;
}

const MainButton: React.FC<MainButtonProps> = ({ onHoldTick, energy }) => {
  const [clicked, setClicked] = useState(false);

  const handleClick = () => {
    if (energy <= 0) return;

    setClicked(true);
    onHoldTick();

    // сбросим "clicked" через 150мс
    setTimeout(() => setClicked(false), 150);
  };

  return (
    <button
      onClick={handleClick}
      disabled={energy <= 0}
      className={`w-64 h-64 rounded-full overflow-hidden border-4 transition-all duration-150
        ${
          energy > 0
            ? `border-[#00f0ff] bg-[#0e1a2b] hover:scale-105 animate-pulseNeon ${clicked ? 'scale-110' : ''}`
            : 'border-gray-500 bg-[#1a1a1a] opacity-50 cursor-not-allowed'
        }
      `}
    >
      <img
        src="./logo.png"
        alt="Main Coin"
        className="w-full h-full object-cover"
      />
    </button>
  );
};

export default MainButton;



