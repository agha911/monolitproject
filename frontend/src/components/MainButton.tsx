import React, { useState, useRef } from 'react';

interface MainButtonProps {
  onMultiClick: (xPercent: number, yPercent: number) => void;
  energy: number;
}

const MainButton: React.FC<MainButtonProps> = ({ onMultiClick, energy }) => {
  const [clicked, setClicked] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const handleTouch = (e: React.TouchEvent) => {
    if (energy <= 0) return;
    setClicked(true);

    const rect = buttonRef.current?.getBoundingClientRect();
    if (!rect) return;

    for (let i = 0; i < e.touches.length; i++) {
      const touch = e.touches[i];
      const xPercent = ((touch.clientX - rect.left) / rect.width) * 100;
      const yPercent = ((touch.clientY - rect.top) / rect.height) * 100;
      onMultiClick(xPercent, yPercent);
    }

    setTimeout(() => setClicked(false), 250);
  };

  const handleClick = (e: React.MouseEvent) => {
    if (energy <= 0 || !buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const xPercent = ((e.clientX - rect.left) / rect.width) * 100;
    const yPercent = ((e.clientY - rect.top) / rect.height) * 100;
    onMultiClick(xPercent, yPercent);
    setClicked(true);
    setTimeout(() => setClicked(false), 250);
  };

  return (
    <button
      ref={buttonRef}
      onClick={handleClick}
      onTouchStart={handleTouch}
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








