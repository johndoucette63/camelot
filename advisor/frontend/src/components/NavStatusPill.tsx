// Persistent VPN status pill in the top navigation (feature 015 US-2 FR-013b).
// Visible on every page so a transition from green→red is unmissable
// regardless of which page the operator is on.

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchVpnStatus, type VpnStatus, type VpnState } from "../services/vpn";

const POLL_INTERVAL_MS = 60_000;

interface PillTheme {
  bg: string;
  text: string;
  dot: string;
  label: string;
  pulse: boolean;
}

const STATE_PILL: Record<VpnState, PillTheme> = {
  OK:                 { bg: "bg-green-100",  text: "text-green-800",  dot: "bg-green-500",  label: "VPN · OK",       pulse: false },
  LEAK_DETECTED:      { bg: "bg-red-100",    text: "text-red-800",    dot: "bg-red-500",    label: "VPN · LEAK",     pulse: true  },
  PROBE_UNREACHABLE:  { bg: "bg-yellow-100", text: "text-yellow-800", dot: "bg-yellow-500", label: "VPN · ?",        pulse: false },
  WATCHDOG_DOWN:      { bg: "bg-gray-200",   text: "text-gray-700",   dot: "bg-gray-500",   label: "VPN · ∅",        pulse: false },
  AUTO_STOPPED:      { bg: "bg-red-200",    text: "text-red-900",    dot: "bg-red-700",    label: "VPN · STOPPED",  pulse: true  },
  UNKNOWN:            { bg: "bg-gray-100",   text: "text-gray-600",   dot: "bg-gray-400",   label: "VPN · …",        pulse: false },
};

function NavStatusPill() {
  const [status, setStatus] = useState<VpnStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await fetchVpnStatus();
        if (!cancelled) setStatus(data);
      } catch {
        // Swallow: the dashboard card surfaces detailed errors. The pill
        // just shows the gray "unknown" state if the endpoint is down.
        if (!cancelled) setStatus(null);
      }
    }
    void load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const state: VpnState = status?.state ?? "UNKNOWN";
  const theme = STATE_PILL[state];
  const tooltip = status?.message ?? "VPN status pending";

  return (
    <Link
      to="/"
      className={`ml-auto inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${theme.bg} ${theme.text} hover:brightness-95`}
      title={tooltip}
      data-vpn-state={state}
    >
      <span
        className={`inline-block h-2 w-2 rounded-full ${theme.dot} ${
          theme.pulse ? "animate-pulse" : ""
        }`}
      />
      {theme.label}
    </Link>
  );
}

export default NavStatusPill;
