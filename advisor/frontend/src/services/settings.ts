import type {
  MuteListResponse,
  NotificationSinkListResponse,
  NotificationTestResponse,
  RuleMute,
  Threshold,
  ThresholdListResponse,
} from "../types";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = body?.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

// ── Thresholds ─────────────────────────────────────────────────────────

export async function fetchThresholds(): Promise<Threshold[]> {
  const res = await fetch("/api/settings/thresholds");
  const body = await handle<ThresholdListResponse>(res);
  return body.thresholds;
}

export async function updateThreshold(
  key: string,
  value: number,
): Promise<Threshold> {
  const res = await fetch(`/api/settings/thresholds/${encodeURIComponent(key)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  return handle<Threshold>(res);
}

// ── Mutes ───────────────────────────────────────────────────────────────

export async function fetchMutes(includeExpired = false): Promise<RuleMute[]> {
  const qs = includeExpired ? "?include_expired=true" : "";
  const res = await fetch(`/api/settings/mutes${qs}`);
  const body = await handle<MuteListResponse>(res);
  return body.mutes;
}

export interface CreateMuteInput {
  rule_id: string;
  target_type: "device" | "service" | "system";
  target_id: number | null;
  duration_seconds: number;
  note?: string;
}

export async function createMute(input: CreateMuteInput): Promise<RuleMute> {
  const res = await fetch("/api/settings/mutes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<RuleMute>(res);
}

export async function cancelMute(id: number): Promise<void> {
  const res = await fetch(`/api/settings/mutes/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    throw new Error(`Failed to cancel mute: ${res.status}`);
  }
}

// ── Notification sinks ─────────────────────────────────────────────────

export async function fetchNotificationSinks() {
  const res = await fetch("/api/settings/notifications");
  const body = await handle<NotificationSinkListResponse>(res);
  return body.sinks;
}

export interface SinkInput {
  type: "home_assistant";
  name: string;
  enabled: boolean;
  endpoint?: string;
  min_severity: "info" | "warning" | "critical";
}

export async function createNotificationSink(input: SinkInput) {
  const res = await fetch("/api/settings/notifications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function updateNotificationSink(id: number, input: Partial<SinkInput>) {
  const res = await fetch(`/api/settings/notifications/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function deleteNotificationSink(id: number): Promise<void> {
  const res = await fetch(`/api/settings/notifications/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    throw new Error(`Failed to delete sink: ${res.status}`);
  }
}

export async function testNotificationSink(
  id: number,
): Promise<NotificationTestResponse> {
  const res = await fetch(`/api/settings/notifications/${id}/test`, {
    method: "POST",
  });
  if (res.status === 502) {
    return (await res.json()) as NotificationTestResponse;
  }
  return handle<NotificationTestResponse>(res);
}
