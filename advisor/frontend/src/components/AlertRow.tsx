import type { Alert, AlertSeverity } from "../types";

const SEVERITY_BADGE: Record<AlertSeverity, string> = {
  critical: "bg-red-100 text-red-800 border border-red-200",
  warning: "bg-amber-100 text-amber-800 border border-amber-200",
  info: "bg-blue-100 text-blue-800 border border-blue-200",
};

const STATE_CLASS: Record<string, string> = {
  active: "text-red-700",
  acknowledged: "text-amber-700",
  resolved: "text-gray-500",
};

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

interface Props {
  alert: Alert;
  onAcknowledge?: (id: number) => void;
  onResolve?: (id: number) => void;
}

export default function AlertRow({ alert, onAcknowledge, onResolve }: Props) {
  const canAck = alert.state === "active";
  const canResolve = alert.state === "active" || alert.state === "acknowledged";

  return (
    <tr className="border-t border-gray-100 align-top" data-testid={`alert-row-${alert.id}`}>
      <td className="px-3 py-2">
        <span
          className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${SEVERITY_BADGE[alert.severity]}`}
        >
          {alert.severity}
        </span>
      </td>
      <td className="px-3 py-2 text-sm text-gray-700">
        {alert.target_label ?? alert.rule_name}
      </td>
      <td className="px-3 py-2 text-sm text-gray-800 max-w-[40ch] truncate">
        {alert.message}
      </td>
      <td
        className={`px-3 py-2 text-xs font-medium ${STATE_CLASS[alert.state] ?? ""}`}
      >
        {alert.state}
      </td>
      <td className="px-3 py-2 text-xs text-gray-500">
        {formatTime(alert.created_at)}
      </td>
      <td className="px-3 py-2 text-right">
        <div className="flex justify-end gap-1">
          {canAck && onAcknowledge ? (
            <button
              type="button"
              onClick={() => onAcknowledge(alert.id)}
              className="rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-gray-100"
            >
              Ack
            </button>
          ) : null}
          {canResolve && onResolve ? (
            <button
              type="button"
              onClick={() => onResolve(alert.id)}
              className="rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-gray-100"
            >
              Resolve
            </button>
          ) : null}
        </div>
      </td>
    </tr>
  );
}
