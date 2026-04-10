const colors: Record<string, { dot: string; label: string; text: string }> = {
  green: { dot: "bg-green-500", label: "Healthy", text: "text-green-700" },
  yellow: { dot: "bg-yellow-500", label: "Degraded", text: "text-yellow-700" },
  red: { dot: "bg-red-500", label: "Down", text: "text-red-700" },
};

interface HealthStatusBadgeProps {
  status: string | null;
}

export function HealthStatusBadge({ status }: HealthStatusBadgeProps) {
  const info = status ? colors[status] : null;
  const dot = info?.dot ?? "bg-gray-400";
  const label = info?.label ?? "Pending";
  const text = info?.text ?? "text-gray-500";

  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${text}`}>
      <span className={`inline-block w-2 h-2 rounded-full ${dot}`} />
      {label}
    </span>
  );
}
