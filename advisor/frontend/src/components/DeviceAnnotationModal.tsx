import { useState } from "react";
import type { Device } from "../types";

const ROLES = [
  "server",
  "workstation",
  "storage",
  "networking",
  "dns",
  "printer",
  "camera",
  "sensor",
  "speaker",
  "appliance",
  "iot",
  "unknown",
];

interface Props {
  device: Device;
  onClose: () => void;
  onSaved: () => void;
}

export function DeviceAnnotationModal({ device, onClose, onSaved }: Props) {
  const [role, setRole] = useState(device.annotation?.role ?? "unknown");
  const [description, setDescription] = useState(device.annotation?.description ?? "");
  const [tagsInput, setTagsInput] = useState(
    (device.annotation?.tags ?? []).join(", ")
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const tags = tagsInput
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      const res = await fetch(`/api/devices/${encodeURIComponent(device.mac_address)}/annotation`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, description: description || null, tags }),
      });

      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = await res.json();
          detail = body.detail ?? detail;
        } catch {}
        throw new Error(detail);
      }

      setSaved(true);
      setTimeout(() => onSaved(), 800);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-1">Annotate Device</h2>
        <p className="text-sm text-gray-500 font-mono">
          {device.hostname ?? device.mac_address} · {device.ip_address}
        </p>
        <p className="text-xs text-gray-400 mb-4">
          Last seen: {new Date(device.last_seen).toLocaleString()}
          {device.vendor ? ` · ${device.vendor}` : ""}
        </p>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Optional description…"
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Tags <span className="text-gray-400 font-normal">(comma-separated)</span>
            </label>
            <input
              type="text"
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              placeholder="e.g. plex, media, lan"
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
        </div>

        {error && (
          <p className="mt-3 text-sm text-red-600">{error}</p>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || saved}
            className={`px-4 py-1.5 text-sm text-white rounded disabled:opacity-75 ${
              saved
                ? "bg-green-600"
                : "bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
            }`}
          >
            {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
