import type {
  HAConnection,
  HAConnectionStatus,
  HAConnectionUpsert,
  HAEntitiesResponse,
  ThreadTopologyResponse,
} from "../types";

export interface HAConnectionError extends Error {
  status: HAConnectionStatus | "invalid_url";
  detail: string;
  httpStatus: number;
}

function makeHAError(
  status: HAConnectionStatus | "invalid_url",
  detail: string,
  httpStatus: number,
): HAConnectionError {
  const err = new Error(detail) as HAConnectionError;
  err.status = status;
  err.detail = detail;
  err.httpStatus = httpStatus;
  return err;
}

async function parseError(res: Response): Promise<HAConnectionError> {
  let status: HAConnectionStatus | "invalid_url" = "unreachable";
  let detail = `HTTP ${res.status}`;
  try {
    const body = (await res.json()) as { status?: string; detail?: string };
    if (body?.detail) detail = body.detail;
    if (body?.status) status = body.status as HAConnectionStatus | "invalid_url";
  } catch {
    /* ignore */
  }
  return makeHAError(status, detail, res.status);
}

async function handleJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    throw await parseError(res);
  }
  return (await res.json()) as T;
}

// ── Connection management ─────────────────────────────────────────────

export async function getHomeAssistantConnection(): Promise<HAConnection> {
  const res = await fetch("/api/settings/home-assistant");
  return handleJson<HAConnection>(res);
}

export async function upsertHomeAssistantConnection(
  body: HAConnectionUpsert,
): Promise<HAConnection> {
  const res = await fetch("/api/settings/home-assistant", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleJson<HAConnection>(res);
}

export async function testHomeAssistantConnection(
  body: HAConnectionUpsert,
): Promise<HAConnection> {
  const res = await fetch("/api/settings/home-assistant/test-connection", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleJson<HAConnection>(res);
}

export async function deleteHomeAssistantConnection(): Promise<void> {
  const res = await fetch("/api/settings/home-assistant", { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    throw await parseError(res);
  }
}

// ── Entity snapshot ────────────────────────────────────────────────────

export interface HAEntitiesParams {
  domain?: string[];
  search?: string;
  stale_only?: boolean;
}

export async function getHomeAssistantEntities(
  params: HAEntitiesParams = {},
): Promise<HAEntitiesResponse> {
  const qs = new URLSearchParams();
  for (const d of params.domain ?? []) qs.append("domain", d);
  if (params.search) qs.set("search", params.search);
  if (params.stale_only) qs.set("stale_only", "true");
  const q = qs.toString();
  const res = await fetch(`/api/ha/entities${q ? `?${q}` : ""}`);
  return handleJson<HAEntitiesResponse>(res);
}

// ── Thread topology ────────────────────────────────────────────────────

export async function getThreadTopology(): Promise<ThreadTopologyResponse> {
  const res = await fetch("/api/ha/thread");
  return handleJson<ThreadTopologyResponse>(res);
}
