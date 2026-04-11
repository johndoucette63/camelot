import type { Alert, AlertListResponse, AlertSeverity, AlertState } from "../types";

export interface AlertFilters {
  severity?: AlertSeverity[];
  state?: AlertState[];
  rule_id?: string;
  device_id?: number;
  service_id?: number;
  since?: string;
  until?: string;
  include_suppressed?: boolean;
  limit?: number;
  offset?: number;
}

function toQuery(filters: AlertFilters): string {
  const params = new URLSearchParams();
  for (const sev of filters.severity ?? []) params.append("severity", sev);
  for (const st of filters.state ?? []) params.append("state", st);
  if (filters.rule_id) params.set("rule_id", filters.rule_id);
  if (filters.device_id !== undefined)
    params.set("device_id", String(filters.device_id));
  if (filters.service_id !== undefined)
    params.set("service_id", String(filters.service_id));
  if (filters.since) params.set("since", filters.since);
  if (filters.until) params.set("until", filters.until);
  if (filters.include_suppressed)
    params.set("include_suppressed", String(filters.include_suppressed));
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export async function fetchAlerts(
  filters: AlertFilters = {},
): Promise<AlertListResponse> {
  const res = await fetch(`/api/alerts${toQuery(filters)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch alerts: ${res.status}`);
  }
  return (await res.json()) as AlertListResponse;
}

export async function acknowledgeAlert(id: number): Promise<Alert> {
  const res = await fetch(`/api/alerts/${id}/acknowledge`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as Alert;
}

export async function resolveAlert(id: number): Promise<Alert> {
  const res = await fetch(`/api/alerts/${id}/resolve`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as Alert;
}
