import { useEffect, useState } from "react";
import type { AlertSeverity, Recommendation, RecommendationsResponse } from "../types";
import { fetchRecommendations } from "../services/recommendations";

const POLL_INTERVAL_MS = 30_000;

const SEVERITY_ORDER: AlertSeverity[] = ["critical", "warning", "info"];

const SEVERITY_BADGE: Record<AlertSeverity, string> = {
  critical: "bg-red-100 text-red-800 border border-red-200",
  warning: "bg-amber-100 text-amber-800 border border-amber-200",
  info: "bg-blue-100 text-blue-800 border border-blue-200",
};

const SEVERITY_HEADING: Record<AlertSeverity, string> = {
  critical: "Critical",
  warning: "Warning",
  info: "Info",
};

function groupBySeverity(
  items: Recommendation[],
): Record<AlertSeverity, Recommendation[]> {
  const groups: Record<AlertSeverity, Recommendation[]> = {
    critical: [],
    warning: [],
    info: [],
  };
  for (const item of items) {
    groups[item.severity].push(item);
  }
  return groups;
}

export default function RecommendationsPanel() {
  const [data, setData] = useState<RecommendationsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetchRecommendations();
        if (!cancelled) {
          setData(res);
          setError(null);
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "unknown error");
        }
      }
    }
    load();
    const id = window.setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  if (error && !data) {
    return (
      <section className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700">
        Failed to load recommendations: {error}
      </section>
    );
  }

  if (!data) {
    return (
      <section className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
        Loading recommendations...
      </section>
    );
  }

  const groups = groupBySeverity(data.active);
  const totalActive = data.active.length;

  return (
    <section
      aria-label="Recommendations"
      className="rounded-lg border border-gray-200 bg-white p-4"
    >
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">
          Recommendations
        </h2>
        <div className="flex gap-2 text-xs">
          <span className={`rounded px-2 py-1 ${SEVERITY_BADGE.critical}`}>
            Critical: {data.counts.critical}
          </span>
          <span className={`rounded px-2 py-1 ${SEVERITY_BADGE.warning}`}>
            Warning: {data.counts.warning}
          </span>
          <span className={`rounded px-2 py-1 ${SEVERITY_BADGE.info}`}>
            Info: {data.counts.info}
          </span>
        </div>
      </header>

      {data.ai_narrative ? (
        <div
          className="mb-3 rounded border border-purple-200 bg-purple-50 p-3 text-sm text-purple-900"
          aria-label="AI-assisted narrative"
        >
          <div className="mb-1 flex items-center gap-2">
            <span className="rounded bg-purple-200 px-2 py-0.5 text-xs font-semibold uppercase text-purple-900">
              AI-assisted
            </span>
            <span className="text-xs text-purple-700">
              {new Date(data.ai_narrative.generated_at).toLocaleString()}
            </span>
          </div>
          <p className="whitespace-pre-wrap">{data.ai_narrative.text}</p>
        </div>
      ) : null}

      {totalActive === 0 ? (
        <p className="py-6 text-center text-sm text-gray-500">
          All clear — no active recommendations.
        </p>
      ) : (
        <div className="space-y-3">
          {SEVERITY_ORDER.map((sev) =>
            groups[sev].length === 0 ? null : (
              <div key={sev}>
                <h3 className="mb-1 text-xs font-semibold uppercase text-gray-500">
                  {SEVERITY_HEADING[sev]}
                </h3>
                <ul className="space-y-1">
                  {groups[sev].map((rec) => (
                    <li
                      key={rec.id}
                      className="flex items-start gap-2 rounded border border-gray-100 bg-gray-50 p-2 text-sm"
                    >
                      <span
                        className={`mt-0.5 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${SEVERITY_BADGE[rec.severity]}`}
                      >
                        {rec.severity}
                      </span>
                      <div className="flex-1">
                        <div className="font-medium text-gray-800">
                          {rec.target_label ?? rec.rule_name}
                        </div>
                        <div className="text-gray-600">{rec.message}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ),
          )}
        </div>
      )}
    </section>
  );
}
