import { useEffect, useState } from "react";
import type { Threshold } from "../types";
import { fetchThresholds, updateThreshold } from "../services/settings";

interface RowState {
  value: string;
  saving: boolean;
  error: string | null;
  dirty: boolean;
}

export default function ThresholdForm() {
  const [thresholds, setThresholds] = useState<Threshold[] | null>(null);
  const [rows, setRows] = useState<Record<string, RowState>>({});
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    fetchThresholds()
      .then((list) => {
        setThresholds(list);
        const initial: Record<string, RowState> = {};
        for (const t of list) {
          initial[t.key] = {
            value: String(t.value),
            saving: false,
            error: null,
            dirty: false,
          };
        }
        setRows(initial);
      })
      .catch((exc) =>
        setLoadError(exc instanceof Error ? exc.message : "load failed"),
      );
  }, []);

  function patchRow(key: string, patch: Partial<RowState>) {
    setRows((prev) => {
      const existing = prev[key];
      if (!existing) return prev;
      return { ...prev, [key]: { ...existing, ...patch } };
    });
  }

  function handleChange(key: string, next: string) {
    patchRow(key, { value: next, dirty: true, error: null });
  }

  async function handleSave(t: Threshold) {
    const row = rows[t.key];
    if (!row) return;
    const parsed = Number(row.value);
    if (!Number.isFinite(parsed)) {
      patchRow(t.key, { error: "must be a number" });
      return;
    }
    if (parsed < t.min_value || parsed > t.max_value) {
      patchRow(t.key, {
        error: `must be between ${t.min_value} and ${t.max_value}`,
      });
      return;
    }
    patchRow(t.key, { saving: true, error: null });
    try {
      const updated = await updateThreshold(t.key, parsed);
      setThresholds((list) =>
        list
          ? list.map((existing) => (existing.key === t.key ? updated : existing))
          : list,
      );
      setRows((prev) => ({
        ...prev,
        [t.key]: {
          value: String(updated.value),
          saving: false,
          error: null,
          dirty: false,
        },
      }));
    } catch (exc) {
      patchRow(t.key, {
        saving: false,
        error: exc instanceof Error ? exc.message : "save failed",
      });
    }
  }

  if (loadError) {
    return (
      <section className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-700">
        Failed to load thresholds: {loadError}
      </section>
    );
  }

  if (!thresholds) {
    return (
      <section className="rounded border border-gray-200 bg-white p-4 text-sm text-gray-500">
        Loading thresholds...
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4">
      <h2 className="mb-3 text-lg font-semibold text-gray-800">Thresholds</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase text-gray-500">
            <th className="pb-2">Key</th>
            <th className="pb-2">Value</th>
            <th className="pb-2">Default</th>
            <th className="pb-2">Range</th>
            <th className="pb-2" />
          </tr>
        </thead>
        <tbody>
          {thresholds.map((t) => {
            const row = rows[t.key];
            return (
              <tr key={t.key} className="border-t border-gray-100">
                <td className="py-2 font-mono text-gray-700">{t.key}</td>
                <td className="py-2">
                  <input
                    type="number"
                    value={row?.value ?? ""}
                    onChange={(e) => handleChange(t.key, e.target.value)}
                    className="w-20 rounded border border-gray-300 px-2 py-1"
                    aria-label={`value for ${t.key}`}
                  />
                  <span className="ml-1 text-gray-500">{t.unit}</span>
                  {row?.error ? (
                    <div className="mt-1 text-xs text-red-600">{row.error}</div>
                  ) : null}
                </td>
                <td className="py-2 text-gray-600">
                  {t.default_value}
                  {t.unit}
                </td>
                <td className="py-2 text-gray-600">
                  {t.min_value}–{t.max_value}
                </td>
                <td className="py-2">
                  <button
                    type="button"
                    onClick={() => handleSave(t)}
                    disabled={!row?.dirty || row?.saving}
                    className="rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white disabled:bg-gray-300"
                  >
                    {row?.saving ? "Saving..." : "Save"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
