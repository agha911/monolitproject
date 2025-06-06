import type { ButtonHTMLAttributes } from 'react';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
}

export default function Button({ children, ...props }: Props) {
  return (
    <button
      {...props}
      className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg shadow font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {children}
    </button>
  );
}