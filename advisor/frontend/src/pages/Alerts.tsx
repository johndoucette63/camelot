import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  Alert,
  AlertListResponse,
  AlertSeverity,
  AlertState,
} from "../types";
import {
  acknowledgeAlert,
  fetchAlerts,
  resolveAlert,
  type AlertFilters,
} from "../services/alerts";
import AlertRow from "../components/AlertRow";

const SEVERITY_OPTIONS: AlertSeverity[] = ["critical", "warning", "info"];
const STATE_OPTIONS: AlertState[] = ["active", "acknowledged", "resolved"];
const PAGE_SIZE = 50;

export default function Alerts() {
  const [data, setData] = useState<AlertListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [severity, setSeverity] = useState<AlertSeverity[]>([]);
  const [state, setState] = useState<AlertState[]>([]);
  const [includeSuppressed, setIncludeSuppressed] = useState(false);
  const [offset, setOffset] = useState(0);

  const filters = useMemo<AlertFilters>(
    () => ({
      severity: severity.length ? severity : undefined,
      state: state.length ? state : undefined,
      include_suppressed: includeSuppressed,
      limit: PAGE_SIZE,
      offset,
    }),
    [severity, state, includeSuppressed, offset],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAlerts(filters);
      setData(res);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "load failed");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  function toggleSeverity(sev: AlertSeverity) {
    setSeverity((prev) =>
      prev.includes(sev) ? prev.filter((s) => s !== sev) : [...prev, sev],
    );
    setOffset(0);
  }

  function toggleState(st: AlertState) {
    setState((prev) =>
      prev.includes(st) ? prev.filter((s) => s !== st) : [...prev, st],
    );
    setOffset(0);
  }

  async function handleAcknowledge(id: number) {
    try {
      await acknowledgeAlert(id);
      void load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "ack failed");
    }
  }

  async function handleResolve(id: number) {
    try {
      await resolveAlert(id);
      void load();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "resolve failed");
    }
  }

  const items: Alert[] = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <h1 className="text-2xl font-bold text-gray-800">Alerts</h1>

      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase text-gray-500">
              Severity
            </span>
            {SEVERITY_OPTIONS.map((sev) => (
              <label key={sev} className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={severity.includes(sev)}
                  onChange={() => toggleSeverity(sev)}
                />
                <span>{sev}</span>
              </label>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase text-gray-500">
              State
            </span>
            {STATE_OPTIONS.map((st) => (
              <label key={st} className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={state.includes(st)}
                  onChange={() => toggleState(st)}
                />
                <span>{st}</span>
              </label>
            ))}
          </div>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={includeSuppressed}
              onChange={(e) => {
                setIncludeSuppressed(e.target.checked);
                setOffset(0);
              }}
            />
            <span>show suppressed</span>
          </label>
        </div>

        {error ? (
          <div className="mb-2 rounded bg-red-50 p-2 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-gray-500">
                <th className="px-3 py-2">Sev</th>
                <th className="px-3 py-2">Target</th>
                <th className="px-3 py-2">Message</th>
                <th className="px-3 py-2">State</th>
                <th className="px-3 py-2">Created</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {loading && items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-4 text-center text-gray-500">
                    Loading...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-4 text-center text-gray-500">
                    No alerts match the current filters.
                  </td>
                </tr>
              ) : (
                items.map((alert) => (
                  <AlertRow
                    key={alert.id}
                    alert={alert}
                    onAcknowledge={handleAcknowledge}
                    onResolve={handleResolve}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
          <span>
            Showing {items.length === 0 ? 0 : offset + 1}–{pageEnd} of {total}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(offset - PAGE_SIZE, 0))}
              className="rounded border border-gray-300 px-2 py-1 disabled:text-gray-300"
            >
              Prev
            </button>
            <button
              type="button"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="rounded border border-gray-300 px-2 py-1 disabled:text-gray-300"
            >
              Next
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
