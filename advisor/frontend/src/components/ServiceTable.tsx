import { useEffect, useState } from "react";
import { HealthStatusBadge } from "./HealthStatusBadge";
import { ServiceDetailModal } from "./ServiceDetailModal";
import type { ServiceWithLatest } from "../types";

const POLL_INTERVAL = 60_000;

interface ServiceTableProps {
  hostsUnreachable?: string[];
}

export function ServiceTable({ hostsUnreachable = [] }: ServiceTableProps) {
  const [services, setServices] = useState<ServiceWithLatest[]>([]);
  const [selected, setSelected] = useState<ServiceWithLatest | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function fetchServices() {
    try {
      const res = await fetch("/api/services");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setServices(await res.json());
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  }

  useEffect(() => {
    fetchServices();
    const id = setInterval(fetchServices, POLL_INTERVAL);
    return () => clearInterval(id);
  }, []);

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
        Failed to load services: {error}
      </div>
    );
  }

  if (services.length === 0) {
    return <p className="text-sm text-gray-500 italic">No services defined yet.</p>;
  }

  // Group services by host_label
  const grouped: Record<string, ServiceWithLatest[]> = {};
  for (const svc of services) {
    (grouped[svc.host_label] ||= []).push(svc);
  }

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-800 mb-3">Service Health</h2>

      {Object.entries(grouped).map(([hostLabel, hostServices]) => {
        const unreachable = hostsUnreachable.includes(hostLabel);

        return (
          <div key={hostLabel} className="mb-4">
            <h3 className="text-sm font-medium text-gray-600 mb-2">{hostLabel}</h3>

            {unreachable ? (
              <div className="px-4 py-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
                Host unreachable — all services on {hostLabel} are down
              </div>
            ) : (
              <div className="bg-white rounded border border-gray-200 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                      <th className="py-2 pr-4 pl-3">Service</th>
                      <th className="py-2 pr-4">Port</th>
                      <th className="py-2 pr-4">Status</th>
                      <th className="py-2 pr-4">Last Check</th>
                    </tr>
                  </thead>
                  <tbody>
                    {hostServices.map((svc) => (
                      <tr
                        key={svc.id}
                        className="border-b border-gray-100 last:border-0 hover:bg-gray-50 cursor-pointer"
                        onClick={() => setSelected(svc)}
                      >
                        <td className="py-2 pr-4 pl-3 font-medium text-gray-800">{svc.name}</td>
                        <td className="py-2 pr-4 text-gray-500 font-mono">{svc.port}</td>
                        <td className="py-2 pr-4">
                          <HealthStatusBadge status={svc.latest?.status ?? null} />
                        </td>
                        <td className="py-2 pr-4 text-gray-400 text-xs">
                          {svc.latest
                            ? new Date(svc.latest.checked_at).toLocaleTimeString()
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}

      {selected && (
        <ServiceDetailModal
          service={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
