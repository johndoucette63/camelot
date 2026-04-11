import { useEffect, useState } from "react";
import type { RuleMute } from "../types";
import { cancelMute, fetchMutes } from "../services/settings";

function formatRemaining(totalSeconds: number): string {
  if (totalSeconds <= 0) return "expired";
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

export default function MuteList() {
  const [mutes, setMutes] = useState<RuleMute[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchMutes()
      .then((list) => {
        if (!cancelled) setMutes(list);
      })
      .catch((exc) => {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "load failed");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleCancel(id: number) {
    try {
      await cancelMute(id);
      setMutes((list) => (list ? list.filter((m) => m.id !== id) : list));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "cancel failed");
    }
  }

  if (error && !mutes) {
    return (
      <section className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-700">
        Failed to load mutes: {error}
      </section>
    );
  }

  if (!mutes) {
    return (
      <section className="rounded border border-gray-200 bg-white p-4 text-sm text-gray-500">
        Loading mutes...
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4">
      <h2 className="mb-3 text-lg font-semibold text-gray-800">Active mutes</h2>
      {error ? (
        <div className="mb-2 rounded bg-red-50 p-2 text-xs text-red-700">{error}</div>
      ) : null}
      {mutes.length === 0 ? (
        <p className="text-sm text-gray-500">No active mutes.</p>
      ) : (
        <ul className="space-y-2">
          {mutes.map((m) => {
            const now = Date.now() + tick * 0; // dependency trigger only
            const expires = Date.parse(m.expires_at);
            const remainingMs = Math.max(expires - now, 0);
            const remainingSec = Math.floor(remainingMs / 1000);
            return (
              <li
                key={m.id}
                className="flex items-start justify-between gap-2 rounded border border-gray-100 bg-gray-50 p-3"
              >
                <div className="flex-1 text-sm">
                  <div className="font-medium text-gray-800">
                    {m.rule_name}
                    {m.target_label ? (
                      <span className="text-gray-500"> · {m.target_label}</span>
                    ) : null}
                  </div>
                  {m.note ? (
                    <div className="text-xs text-gray-600">{m.note}</div>
                  ) : null}
                  <div className="text-xs text-gray-500">
                    expires in {formatRemaining(remainingSec)}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleCancel(m.id)}
                  className="rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-100"
                >
                  Cancel
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
