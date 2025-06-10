import React from 'react';

interface FriendInviteButtonProps {
  invited: boolean;
  onClick: () => void;
  position: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
}

const positionStyles: Record<FriendInviteButtonProps['position'], string> = {
  'top-left': 'top-4 left-4',
  'top-right': 'top-4 right-4',
  'bottom-left': 'bottom-4 left-4',
  'bottom-right': 'bottom-4 right-4',
};

const FriendInviteButton: React.FC<FriendInviteButtonProps> = ({
  invited,
  onClick,
  position,
}) => {
  const baseStyle = 'absolute w-12 h-12 rounded-full flex items-center justify-center text-xl font-bold transition-all duration-300';
  const glow = invited
    ? 'bg-red-600 shadow-[0_0_12px_3px_#ff3b3b] text-white cursor-default'
    : 'bg-[#00ff9d] shadow-[0_0_12px_3px_#00ffcc] text-black hover:scale-110';

  return (
    <button
      onClick={onClick}
      disabled={invited}
      className={`${baseStyle} ${positionStyles[position]} ${glow}`}
      title={invited ? 'Friend invited!' : 'Invite a friend'}
    >
      {invited ? '✓' : '+'}
    </button>
  );
};

export default FriendInviteButton;

