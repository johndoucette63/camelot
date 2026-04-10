import { useEffect, useState } from "react";
import type { DashboardSummary as DashboardSummaryType } from "../types";

const POLL_INTERVAL = 60_000;

interface DashboardSummaryProps {
  onHostsUnreachable?: (hosts: string[]) => void;
}

export function DashboardSummary({ onHostsUnreachable }: DashboardSummaryProps) {
  const [data, setData] = useState<DashboardSummaryType | null>(null);

  async function fetchSummary() {
    try {
      const res = await fetch("/api/dashboard/summary");
      if (!res.ok) return;
      const summary: DashboardSummaryType = await res.json();
      setData(summary);
      onHostsUnreachable?.(summary.hosts_unreachable);
    } catch {
      // silently retry next cycle
    }
  }

  useEffect(() => {
    fetchSummary();
    const id = setInterval(fetchSummary, POLL_INTERVAL);
    return () => clearInterval(id);
  }, []);

  if (!data) return null;

  const allHealthy = data.healthy === data.total && data.total > 0;

  return (
    <div className="mb-6">
      {/* Unreachable hosts alert */}
      {data.hosts_unreachable.length > 0 && (
        <div className="mb-3 px-4 py-3 bg-red-50 border border-red-300 rounded-lg text-sm text-red-800 font-medium">
          Host{data.hosts_unreachable.length > 1 ? "s" : ""} unreachable:{" "}
          {data.hosts_unreachable.join(", ")}
        </div>
      )}

      {/* Summary banner */}
      <div
        className={`px-5 py-4 rounded-lg border ${
          allHealthy
            ? "bg-green-50 border-green-200"
            : data.down > 0
              ? "bg-red-50 border-red-200"
              : "bg-yellow-50 border-yellow-200"
        }`}
      >
        <div className="flex items-center gap-4 flex-wrap">
          <span className="text-lg font-semibold text-gray-800">
            {data.healthy} / {data.total} services healthy
          </span>
          <div className="flex gap-2">
            {data.healthy > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                {data.healthy} healthy
              </span>
            )}
            {data.degraded > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700">
                <span className="w-1.5 h-1.5 rounded-full bg-yellow-500" />
                {data.degraded} degraded
              </span>
            )}
            {data.down > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                {data.down} down
              </span>
            )}
            {data.unchecked > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                {data.unchecked} pending
              </span>
            )}
          </div>
        </div>

        {/* Per-host breakdown */}
        <div className="mt-3 flex gap-4 flex-wrap text-xs text-gray-600">
          {data.hosts.map((h) => (
            <span key={h.label}>
              <span className="font-medium">{h.label}</span>:{" "}
              {h.healthy}/{h.total}
              {h.degraded > 0 && <span className="text-yellow-600 ml-1">({h.degraded} degraded)</span>}
              {h.down > 0 && <span className="text-red-600 ml-1">({h.down} down)</span>}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
