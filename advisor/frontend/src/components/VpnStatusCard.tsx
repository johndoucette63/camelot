// Prominent VPN tunnel-health card for the dashboard (feature 015 US-2 FR-013).
// Top of the Home page. Renders one of six visually-distinct states per
// data-model.md E7 "Frontend mapping" table.

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchVpnStatus, type VpnStatus, type VpnState } from "../services/vpn";

const POLL_INTERVAL_MS = 60_000;

interface Theme {
  border: string;
  bg: string;
  text: string;
  dot: string;
  label: string;
}

const STATE_THEME: Record<VpnState, Theme> = {
  OK: {
    border: "border-green-600",
    bg: "bg-green-900/30",
    text: "text-green-300",
    dot: "bg-green-500",
    label: "VPN OK",
  },
  LEAK_DETECTED: {
    border: "border-red-600",
    bg: "bg-red-900/40",
    text: "text-red-300",
    dot: "bg-red-500",
    label: "LEAK DETECTED",
  },
  PROBE_UNREACHABLE: {
    border: "border-yellow-600",
    bg: "bg-yellow-900/30",
    text: "text-yellow-300",
    dot: "bg-yellow-500",
    label: "Probe Unreachable",
  },
  WATCHDOG_DOWN: {
    border: "border-gray-500",
    bg: "bg-gray-700/40",
    text: "text-gray-300",
    dot: "bg-gray-400",
    label: "Watchdog Down",
  },
  AUTO_STOPPED: {
    border: "border-red-700",
    bg: "bg-red-900/50",
    text: "text-red-200",
    dot: "bg-red-600",
    label: "AUTO-STOPPED",
  },
  UNKNOWN: {
    border: "border-gray-600",
    bg: "bg-gray-800",
    text: "text-gray-400",
    dot: "bg-gray-500",
    label: "Awaiting Probe",
  },
};

function VpnStatusCard() {
  const [status, setStatus] = useState<VpnStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await fetchVpnStatus();
        if (!cancelled) {
          setStatus(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }
    void load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (error && !status) {
    const t = STATE_THEME.WATCHDOG_DOWN;
    return (
      <section className={`mb-8 rounded-lg border ${t.border} ${t.bg} p-6`}>
        <div className="flex items-center gap-3">
          <span className={`inline-block h-3 w-3 rounded-full ${t.dot}`} />
          <span className={t.text}>VPN status endpoint unreachable: {error}</span>
        </div>
      </section>
    );
  }

  if (!status) {
    return (
      <section className="mb-8 rounded-lg border border-gray-700 bg-gray-800 p-6">
        <div className="flex items-center gap-3">
          <span className="inline-block h-3 w-3 rounded-full bg-gray-500 animate-pulse" />
          <span className="text-gray-400">Loading VPN status…</span>
        </div>
      </section>
    );
  }

  const theme = STATE_THEME[status.state];
  const isLeakLike = status.state === "LEAK_DETECTED" || status.state === "AUTO_STOPPED";
  const alertId = status.active_remediation_alert_id ?? status.active_alert_id;

  return (
    <section
      className={`mb-8 rounded-lg border-2 ${theme.border} ${theme.bg} p-6`}
      role={isLeakLike ? "alert" : undefined}
      data-vpn-state={status.state}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span
            className={`inline-block h-4 w-4 rounded-full ${theme.dot} ${
              isLeakLike ? "animate-pulse" : ""
            }`}
          />
          <div>
            <div className={`text-lg font-semibold ${theme.text}`}>{theme.label}</div>
            <div className="text-sm text-gray-400">{status.message}</div>
          </div>
        </div>
        {isLeakLike && alertId !== null && (
          <Link
            to="/alerts"
            className="rounded bg-red-700 px-3 py-2 text-sm font-medium text-white hover:bg-red-600"
          >
            View alert
          </Link>
        )}
      </div>
    </section>
  );
}

export default VpnStatusCard;
