import { useEffect, useState } from "react";
import type { AlertSeverity, NotificationSink, NotificationTestResponse } from "../types";
import {
  createNotificationSink,
  deleteNotificationSink,
  fetchNotificationSinks,
  testNotificationSink,
  updateNotificationSink,
} from "../services/settings";

interface Draft {
  name: string;
  endpoint: string;
  enabled: boolean;
  min_severity: AlertSeverity;
}

const EMPTY_DRAFT: Draft = {
  name: "",
  endpoint: "",
  enabled: false,
  min_severity: "critical",
};

export default function NotificationSinkForm() {
  const [sinks, setSinks] = useState<NotificationSink[] | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<
    (NotificationTestResponse & { sinkId: number }) | null
  >(null);

  async function reload() {
    try {
      const list = await fetchNotificationSinks();
      setSinks(list);
      if (list[0]) {
        setEditingId(list[0].id);
        setDraft({
          name: list[0].name,
          endpoint: list[0].endpoint_masked,
          enabled: list[0].enabled,
          min_severity: list[0].min_severity,
        });
      } else {
        setEditingId(null);
        setDraft(EMPTY_DRAFT);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "load failed");
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      if (editingId !== null) {
        const payload: Partial<Draft> = {
          name: draft.name,
          enabled: draft.enabled,
          min_severity: draft.min_severity,
        };
        // Only send endpoint if user typed a new URL (not the masked value)
        if (!draft.endpoint.includes("***")) {
          (payload as any).endpoint = draft.endpoint;
        }
        await updateNotificationSink(editingId, payload as any);
      } else {
        await createNotificationSink({
          type: "home_assistant",
          name: draft.name,
          enabled: draft.enabled,
          endpoint: draft.endpoint,
          min_severity: draft.min_severity,
        });
      }
      await reload();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    setError(null);
    try {
      await deleteNotificationSink(id);
      await reload();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "delete failed");
    }
  }

  async function handleTest(id: number) {
    setTestResult(null);
    try {
      const res = await testNotificationSink(id);
      setTestResult({ ...res, sinkId: id });
    } catch (exc) {
      setTestResult({
        sinkId: id,
        ok: false,
        error: exc instanceof Error ? exc.message : "test failed",
      });
    }
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4">
      <h2 className="mb-3 text-lg font-semibold text-gray-800">
        Home Assistant notifications
      </h2>

      {error ? (
        <div className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <div className="space-y-3">
        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold uppercase text-gray-500">
            Name
          </span>
          <input
            type="text"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            className="w-full rounded border border-gray-300 px-2 py-1"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold uppercase text-gray-500">
            Webhook URL
          </span>
          <input
            type="password"
            value={draft.endpoint}
            onChange={(e) => setDraft({ ...draft, endpoint: e.target.value })}
            className="w-full rounded border border-gray-300 px-2 py-1 font-mono"
            placeholder="http://homeassistant.holygrail/api/webhook/..."
          />
          {editingId !== null && draft.endpoint.includes("***") ? (
            <span className="mt-1 block text-xs text-gray-500">
              Leave unchanged to keep the stored value; type a new URL to replace it.
            </span>
          ) : null}
        </label>

        <div className="flex items-center gap-4">
          <label className="flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
            />
            <span>Enabled</span>
          </label>

          <label className="flex items-center gap-1 text-sm">
            <span className="text-xs uppercase text-gray-500">Min severity</span>
            <select
              value={draft.min_severity}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  min_severity: e.target.value as AlertSeverity,
                })
              }
              className="rounded border border-gray-300 px-2 py-1"
            >
              <option value="info">info</option>
              <option value="warning">warning</option>
              <option value="critical">critical</option>
            </select>
          </label>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white disabled:bg-gray-300"
          >
            {saving ? "Saving..." : editingId !== null ? "Update" : "Create"}
          </button>
          {editingId !== null ? (
            <>
              <button
                type="button"
                onClick={() => handleTest(editingId)}
                className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-100"
              >
                Test
              </button>
              <button
                type="button"
                onClick={() => handleDelete(editingId)}
                className="rounded border border-red-300 px-3 py-1 text-sm text-red-700 hover:bg-red-50"
              >
                Delete
              </button>
            </>
          ) : null}
        </div>

        {testResult ? (
          <div
            className={`rounded p-2 text-xs ${
              testResult.ok
                ? "bg-green-50 text-green-800"
                : "bg-red-50 text-red-700"
            }`}
          >
            {testResult.ok
              ? `Delivered in ${testResult.latency_ms ?? "?"} ms (HTTP ${testResult.status_code ?? "?"})`
              : `Failed: ${testResult.error ?? "unknown error"}`}
          </div>
        ) : null}

        {sinks && sinks[0] ? (
          <div className="mt-3 border-t border-gray-100 pt-3 text-xs text-gray-600">
            <div className="font-semibold uppercase text-gray-500">
              Stored endpoint
            </div>
            <div className="font-mono">{sinks[0].endpoint_masked}</div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
