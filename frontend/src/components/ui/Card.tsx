import { ReactNode } from 'react';

export default function Card({ children }: { children: ReactNode }) {
  return (
    <div className="bg-white shadow-lg rounded-xl p-6 w-full">
      {children}
    </div>
  );
}