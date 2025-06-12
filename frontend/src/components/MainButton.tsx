import React, { useState } from 'react';

interface MainButtonProps {
  onClick: () => void;
  energy: number;
}

const MainButton: React.FC<MainButtonProps> = ({ onClick, energy }) => {
  const [clicked, setClicked] = useState(false);

  const handleClick = () => {
    if (energy <= 0) return;
    setClicked(true);
    onClick();
    setTimeout(() => setClicked(false), 250); // чуть длиннее для мягкости
  };

  return (
    <button
      onClick={handleClick}
      disabled={energy <= 0}
      className={`w-72 h-72 rounded-full overflow-hidden border-4 transition-transform duration-300 ease-in-out
        will-change-transform
        ${
          energy > 0
            ? `${clicked ? 'scale-90' : 'scale-100'} border-[#00f0ff] bg-[#0e1a2b] shadow-[0_0_25px_#00f0ff]`
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







