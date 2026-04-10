export interface Annotation {
  role: string;
  description: string | null;
  tags: string[];
}

export interface Device {
  mac_address: string;
  ip_address: string;
  hostname: string | null;
  vendor: string | null;
  first_seen: string;
  last_seen: string;
  is_online: boolean;
  is_known_device: boolean;
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
