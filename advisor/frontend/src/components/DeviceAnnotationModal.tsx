import { useState } from "react";
import type { Device } from "../types";
import { NotesList } from "./NotesList";

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

function EnrichmentDetail({ device }: { device: Device }) {
  const fields: { label: string; value: string | null | undefined }[] = [
    { label: "OS Family", value: device.os_family },
    { label: "OS Detail", value: device.os_detail },
    { label: "mDNS Name", value: device.mdns_name },
    { label: "NetBIOS Name", value: device.netbios_name },
    { label: "SSDP Friendly Name", value: device.ssdp_friendly_name },
    { label: "SSDP Model", value: device.ssdp_model },
    { label: "Classification", value: device.annotation?.classification_source
        ? `${device.annotation.classification_source}${device.annotation.classification_confidence ? ` (${device.annotation.classification_confidence})` : ""}`
        : null },
    { label: "Last Enriched", value: device.last_enriched_at
        ? new Date(device.last_enriched_at).toLocaleString()
        : null },
  ];

  return (
    <div className="space-y-2">
      {fields.map(({ label, value }) => (
        <div key={label} className="flex text-sm">
          <span className="w-40 flex-shrink-0 text-gray-500">{label}</span>
          <span className={value ? "text-gray-800" : "text-gray-400"}>
            {value ?? "—"}
          </span>
        </div>
      ))}
    </div>
  );
}

interface Props {
  device: Device;
  onClose: () => void;
  onSaved: () => void;
}

export function DeviceAnnotationModal({ device, onClose, onSaved }: Props) {
  const [tab, setTab] = useState<"annotation" | "identification" | "notes">("annotation");
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6 max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-1">
          <h2 className="text-lg font-semibold text-gray-800">Device Details</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            aria-label="Close"
          >
            &times;
          </button>
        </div>
        <p className="text-sm text-gray-500 font-mono">
          {device.hostname ?? device.mac_address} · {device.ip_address}
        </p>
        <p className="text-xs text-gray-400 mb-3">
          Last seen: {new Date(device.last_seen).toLocaleString()}
          {device.vendor ? ` · ${device.vendor}` : ""}
        </p>

        <div className="flex gap-1 border-b border-gray-200 mb-4">
          <button
            onClick={() => setTab("annotation")}
            className={`px-3 py-1.5 text-sm font-medium border-b-2 -mb-px ${
              tab === "annotation"
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            Annotation
          </button>
          <button
            onClick={() => setTab("identification")}
            className={`px-3 py-1.5 text-sm font-medium border-b-2 -mb-px ${
              tab === "identification"
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            Identification
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

        <div className="overflow-y-auto flex-1">
          {tab === "annotation" ? (
            <>
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
            </>
          ) : tab === "identification" ? (
            <EnrichmentDetail device={device} />
          ) : (
            <NotesList targetType="device" targetId={device.id} />
          )}
        </div>
      </div>
    </div>
  );
}
