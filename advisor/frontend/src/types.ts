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
