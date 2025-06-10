import React from 'react';

interface FriendInviteButtonProps {
  invited: boolean; // true — приглашён, false — ещё нет
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
  return (
    <button
      onClick={onClick}
      disabled={invited}
      className={`
        absolute w-12 h-12 rounded-full transition-all duration-300
        ${positionStyles[position]}
        ${invited ? 'bg-green-400 cursor-default' : 'bg-yellow-400 hover:scale-105'}
      `}
      title={invited ? 'Friend invited!' : 'Invite a friend'}
    >
      {invited ? '✓' : '+'}
    </button>
  );
};

export default FriendInviteButton;
