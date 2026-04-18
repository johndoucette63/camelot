import { useEffect, useState } from "react";
import type { Alert, AlertDeliveryStatus, AlertSeverity } from "../types";

const SEVERITY_BADGE: Record<AlertSeverity, string> = {
  critical: "bg-red-100 text-red-800 border border-red-200",
  warning: "bg-amber-100 text-amber-800 border border-amber-200",
  info: "bg-blue-100 text-blue-800 border border-blue-200",
};

const DELIVERY_BADGE: Record<AlertDeliveryStatus, string> = {
  sent: "bg-green-100 text-green-800 border border-green-200",
  failed: "bg-amber-100 text-amber-800 border border-amber-200",
  terminal: "bg-red-100 text-red-800 border border-red-200",
  suppressed: "bg-gray-100 text-gray-700 border border-gray-200",
  "n/a": "bg-gray-50 text-gray-500 border border-gray-200",
  pending: "bg-blue-50 text-blue-700 border border-blue-200",
};

function renderDelivery(alert: Alert): { label: string; title: string } {
  const status: AlertDeliveryStatus = alert.delivery_status ?? "pending";
  const attempts = alert.delivery_attempt_count ?? 0;
  switch (status) {
    case "sent":
      return { label: "Sent", title: "Delivered to Home Assistant" };
    case "failed":
      return {
        label: `Retrying (${attempts}/4)`,
        title: "Delivery failed — next retry scheduled",
      };
    case "terminal":
      return {
        label: "Failed (no HA)",
        title: "Retry budget exhausted — check Home Assistant",
      };
    case "suppressed":
      return { label: "Muted", title: "Alert muted — no notification sent" };
    case "n/a":
      return {
        label: "—",
        title: "Below severity threshold or no HA sink configured",
      };
    case "pending":
    default:
      return { label: "Pending", title: "Awaiting initial delivery" };
  }
}

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

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h < 24) return m > 0 ? `${h}h ${m}m` : `${h}h`;
  const d = Math.floor(h / 24);
  const rh = h % 24;
  return rh > 0 ? `${d}d ${rh}h` : `${d}d`;
}

function computeDowntimeMinutes(lastSeen: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(lastSeen).getTime()) / 60_000));
}

/** Returns live downtime text for active device_offline alerts. */
function useLiveDowntime(alert: Alert): string | null {
  const isLive =
    alert.rule_id === "device_offline" &&
    alert.state !== "resolved" &&
    alert.device_last_seen !== undefined &&
    alert.device_last_seen !== null;

  const [text, setText] = useState<string | null>(() => {
    if (!isLive) return null;
    const label = alert.target_label ?? "Device";
    const mins = computeDowntimeMinutes(alert.device_last_seen!);
    return `${label} has been offline for ${formatDuration(mins)}`;
  });

  useEffect(() => {
    if (!isLive) {
      setText(null);
      return;
    }
    const update = () => {
      const label = alert.target_label ?? "Device";
      const mins = computeDowntimeMinutes(alert.device_last_seen!);
      setText(`${label} has been offline for ${formatDuration(mins)}`);
    };
    update();
    const id = setInterval(update, 60_000);
    return () => clearInterval(id);
  }, [isLive, alert.device_last_seen, alert.target_label]);

  return text;
}

interface Props {
  alert: Alert;
  onAcknowledge?: (id: number) => void;
  onResolve?: (id: number) => void;
}

export default function AlertRow({ alert, onAcknowledge, onResolve }: Props) {
  const canAck = alert.state === "active";
  const canResolve = alert.state === "active" || alert.state === "acknowledged";
  const liveMessage = useLiveDowntime(alert);
  const deliveryStatus: AlertDeliveryStatus = alert.delivery_status ?? "pending";
  const { label: deliveryLabel, title: deliveryTitle } = renderDelivery(alert);

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
        {liveMessage ?? alert.message}
      </td>
      <td
        className={`px-3 py-2 text-xs font-medium ${STATE_CLASS[alert.state] ?? ""}`}
      >
        {alert.state}
      </td>
      <td className="px-3 py-2 text-xs">
        <span
          title={deliveryTitle}
          data-testid={`alert-delivery-${deliveryStatus}`}
          className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold ${DELIVERY_BADGE[deliveryStatus]}`}
        >
          {deliveryLabel}
        </span>
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
