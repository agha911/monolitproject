interface Props {
  value: number;
  max: number;
  color?: string;
}

export default function ProgressBar({ value, max, color = 'bg-blue-500' }: Props) {
  const percentage = Math.min((value / max) * 100, 100);

  return (
    <div className="w-full h-4 bg-gray-300 rounded overflow-hidden">
      <div
        className={`h-full transition-all duration-300 ${color}`}
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
}