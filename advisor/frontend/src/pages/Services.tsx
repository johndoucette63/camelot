import { useEffect, useState } from "react";
import { ContainerList } from "../components/ContainerList";
import { DashboardSummary } from "../components/DashboardSummary";
import { ServiceTable } from "../components/ServiceTable";
import { StackUpdater } from "../components/StackUpdater";
import type { ContainerState } from "../types";

const POLL_INTERVAL = 60_000;

export function Services() {
  const [containers, setContainers] = useState<ContainerState | null>(null);
  const [hostsUnreachable, setHostsUnreachable] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function fetchContainers() {
    try {
      const res = await fetch("/api/containers");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setContainers(await res.json());
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  }

  useEffect(() => {
    fetchContainers();
    const id = setInterval(fetchContainers, POLL_INTERVAL);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">Services</h1>

      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
          Failed to load data: {error}
        </div>
      )}

      {/* Dashboard summary banner */}
      <DashboardSummary onHostsUnreachable={setHostsUnreachable} />

      {/* Service health table */}
      <div className="mb-8">
        <ServiceTable hostsUnreachable={hostsUnreachable} />
      </div>

      {/* Stack updates — pull + redeploy buttons */}
      <div className="mb-8">
        <StackUpdater />
      </div>

      {/* Container inventory */}
      <div className="mb-8">
        {containers ? (
          <ContainerList data={containers} />
        ) : (
          !error && (
            <div className="space-y-2">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-8 bg-gray-100 rounded animate-pulse" />
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
}
