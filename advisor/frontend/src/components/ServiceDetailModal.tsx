import { useEffect, useState } from "react";
import { HealthStatusBadge } from "./HealthStatusBadge";
import { NotesList } from "./NotesList";
import type { ServiceWithLatest, ServiceHistoryResponse, HealthCheckResultEntry } from "../types";

interface ServiceDetailModalProps {
  service: ServiceWithLatest;
  onClose: () => void;
}

export function ServiceDetailModal({ service, onClose }: ServiceDetailModalProps) {
  const [tab, setTab] = useState<"health" | "notes">("health");
  const [history, setHistory] = useState<HealthCheckResultEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/services/${service.id}/history?hours=24`)
      .then((res) => res.json())
      .then((data: ServiceHistoryResponse) => setHistory(data.history))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [service.id]);

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">{service.name}</h2>
            <p className="text-sm text-gray-500">
              {service.host_label} &middot; {service.host}:{service.port} &middot; {service.check_type.toUpperCase()}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            aria-label="Close"
          >
            &times;
          </button>
        </div>

        {/* Tabs */}
        <div className="px-5 flex gap-1 border-b border-gray-200">
          <button
            onClick={() => setTab("health")}
            className={`px-3 py-1.5 text-sm font-medium border-b-2 -mb-px ${
              tab === "health"
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            Health History
          </button>
          <button
            onClick={() => setTab("notes")}
            className={`px-3 py-1.5 text-sm font-medium border-b-2 -mb-px ${
              tab === "notes"
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            Notes
          </button>
        </div>

        {/* Content */}
        <div className="px-5 py-4 overflow-y-auto flex-1">
          {tab === "notes" ? (
            <NotesList targetType="service" targetId={service.id} />
          ) : (
          <>
          <h3 className="text-sm font-medium text-gray-600 mb-3">Health History (last 24h)</h3>
          {loading ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-6 bg-gray-100 rounded animate-pulse" />
              ))}
            </div>
          ) : history.length === 0 ? (
            <p className="text-sm text-gray-400 italic">No check results yet.</p>
          ) : (
            <div className="space-y-1">
              {history.map((entry, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-sm py-1 border-b border-gray-50 last:border-0"
                >
                  <div className="flex items-center gap-3">
                    <HealthStatusBadge status={entry.status} />
                    {entry.response_time_ms != null && (
                      <span className="text-gray-400 text-xs">{entry.response_time_ms}ms</span>
                    )}
                  </div>
                  <span className="text-gray-400 text-xs">
                    {new Date(entry.checked_at).toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          )}
          {(() => {
            const last = history.length > 0 ? history[history.length - 1] : undefined;
            return last?.error ? (
              <p className="mt-2 text-xs text-red-600 bg-red-50 rounded px-2 py-1">
                Last error: {last.error}
              </p>
            ) : null;
          })()}
          </>
          )}
        </div>
      </div>
    </div>
  );
}
