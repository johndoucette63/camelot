// Typed client for GET /api/vpn-status (feature 015 US-2).
// Six-state contract documented in specs/015-vpn-sidecar/contracts/README.md.

export type VpnState =
  | "OK"
  | "LEAK_DETECTED"
  | "PROBE_UNREACHABLE"
  | "WATCHDOG_DOWN"
  | "AUTO_STOPPED"
  | "UNKNOWN";

export interface VpnStatus {
  state: VpnState;
  observed_ip: string | null;
  last_probe_at: string | null;
  last_probe_age_seconds: number | null;
  active_alert_id: number | null;
  active_remediation_alert_id: number | null;
  message: string;
}

export async function fetchVpnStatus(): Promise<VpnStatus> {
  const res = await fetch("/api/vpn-status");
  if (!res.ok) {
    throw new Error(`Failed to fetch VPN status: ${res.status}`);
  }
  return (await res.json()) as VpnStatus;
}
