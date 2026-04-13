interface StatusDotProps {
  isOnline: boolean;
}

export function StatusDot({ isOnline }: StatusDotProps) {
  return (
    <span
      title={isOnline ? "Online" : "Offline"}
      className={`inline-block w-2.5 h-2.5 rounded-full ${isOnline ? "bg-green-500" : "bg-red-500"}`}
    />
  );
}
