export interface Annotation {
  role: string;
  description: string | null;
  tags: string[];
}

export interface Device {
  id: number;
  mac_address: string;
  ip_address: string;
  hostname: string | null;
  vendor: string | null;
  first_seen: string;
  last_seen: string;
  is_online: boolean;
  is_known_device: boolean;
  monitor_offline: boolean;
  annotation: Annotation | null;
}

export interface Scan {
  id: number;
  started_at: string;
  completed_at: string | null;
  status: string;
  devices_found: number | null;
  new_devices: number | null;
  error_detail: string | null;
}

export interface EventDevice {
  mac_address: string;
  ip_address: string;
  hostname: string | null;
  vendor: string | null;
}

export interface NetworkEvent {
  id: number;
  event_type: string;
  timestamp: string;
  device: EventDevice | null;
  details: Record<string, unknown> | null;
}

export interface EventsResponse {
  total: number;
  events: NetworkEvent[];
}

export interface AiContextDevice {
  mac: string;
  ip: string;
  hostname: string | null;
  role: string;
  description: string | null;
  tags: string[];
  is_online: boolean;
}

export interface AiContextEvent {
  event_type: string;
  timestamp: string;
  device_mac: string | null;
  device_hostname: string | null;
  details: Record<string, unknown> | null;
}

export interface AiContext {
  devices: AiContextDevice[];
  events: AiContextEvent[];
}

// ── Service Registry & Health Dashboard ─────────────────────────────────

export interface ContainerInfo {
  id: string;
  name: string;
  image: string;
  status: string;
  ports: Record<string, unknown>;
  uptime: string;
  created: string;
}

export interface ContainerState {
  running: ContainerInfo[];
  stopped: ContainerInfo[];
  refreshed_at: string | null;
  socket_error: boolean;
}

export interface HealthCheckResultEntry {
  checked_at: string;
  status: string;
  response_time_ms: number | null;
  error: string | null;
}

export interface ServiceDefinition {
  id: number;
  name: string;
  host_label: string;
  host: string;
  port: number;
  check_type: string;
  enabled: boolean;
}

export interface ServiceWithLatest extends ServiceDefinition {
  latest: HealthCheckResultEntry | null;
}

export interface ServiceHistoryResponse {
  service: ServiceDefinition;
  history: HealthCheckResultEntry[];
}

export interface HostSummary {
  label: string;
  total: number;
  healthy: number;
  degraded: number;
  down: number;
}

export interface DashboardSummary {
  total: number;
  healthy: number;
  degraded: number;
  down: number;
  unchecked: number;
  hosts: HostSummary[];
  hosts_unreachable: string[];
}

// ── Chat ────────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  finished_at: string | null;
  cancelled: boolean;
}

export interface ChatConversation {
  id: number;
  created_at: string;
  updated_at: string;
  title: string | null;
  messages: ChatMessage[];
}

export type ChatFrame =
  | { type: "start"; message_id: number }
  | { type: "token"; content: string }
  | { type: "done"; message_id: number; duration_ms: number; cancelled: boolean }
  | { type: "error"; message_id: number; message: string };

// ── Recommendations & Alerts ────────────────────────────────────────────

export type AlertSeverity = "info" | "warning" | "critical";
export type AlertState = "active" | "acknowledged" | "resolved";
export type AlertTargetType = "device" | "service" | "system";
export type AlertResolutionSource = "auto" | "manual";
export type AlertSource = "rule" | "ai";

export interface Alert {
  id: number;
  rule_id: string;
  rule_name: string;
  severity: AlertSeverity;
  target_type: AlertTargetType;
  target_id: number | null;
  target_label: string | null;
  message: string;
  state: AlertState;
  source: AlertSource;
  suppressed?: boolean;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at?: string | null;
  resolution_source?: AlertResolutionSource | null;
}

export interface AlertListResponse {
  total: number;
  items: Alert[];
  limit: number;
  offset: number;
}

export interface Recommendation extends Alert {}

export interface SeverityCounts {
  critical: number;
  warning: number;
  info: number;
}

export interface AiNarrative {
  text: string;
  generated_at: string;
  source: "ollama";
}

export interface RecommendationsResponse {
  active: Recommendation[];
  counts: SeverityCounts;
  ai_narrative: AiNarrative | null;
}

export interface Threshold {
  key: string;
  value: number;
  unit: string;
  default_value: number;
  min_value: number;
  max_value: number;
  updated_at: string;
}

export interface ThresholdListResponse {
  thresholds: Threshold[];
}

export interface RuleMute {
  id: number;
  rule_id: string;
  rule_name: string;
  target_type: AlertTargetType;
  target_id: number | null;
  target_label: string | null;
  created_at: string;
  expires_at: string;
  remaining_seconds: number;
  note: string | null;
}

export interface MuteListResponse {
  mutes: RuleMute[];
}

export interface NotificationSink {
  id: number;
  type: "home_assistant";
  name: string;
  enabled: boolean;
  endpoint_masked: string;
  min_severity: AlertSeverity;
  created_at: string;
  updated_at: string;
}

export interface NotificationSinkListResponse {
  sinks: NotificationSink[];
}

export interface NotificationTestResponse {
  ok: boolean;
  status_code?: number;
  latency_ms?: number;
  error?: string;
}

// ── Notes & Playbook ──────────────────────────────────────────────────

export type NoteTargetType = "device" | "service" | "playbook";

export interface Note {
  id: number;
  target_type: NoteTargetType;
  target_id: number | null;
  title: string | null;
  body: string;
  pinned: boolean;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface NoteListResponse {
  notes: Note[];
  total: number;
}

export interface NoteSuggestion {
  target_type: NoteTargetType;
  target_id: number | null;
  target_label: string | null;
  body: string;
}

export interface SuggestNotesResponse {
  suggestions: NoteSuggestion[];
  error?: string;
}
