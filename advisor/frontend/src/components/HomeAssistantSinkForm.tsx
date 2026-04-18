import { useEffect, useState } from "react";
import type { AlertSeverity } from "../types";
import {
  createNotificationSink,
  fetchAvailableHaServices,
} from "../services/settings";

/**
 * HomeAssistantSinkForm — feature 016 / US-3.
 *
 * Admin-facing form for creating a *HA-native* notification sink that
 * targets a specific ``notify.<service>`` on the configured Home
 * Assistant instance. Sits alongside the existing webhook-based
 * NotificationSinkForm under Settings → Notifications.
 *
 * Behaviour:
 *
 * * On mount, fetch ``GET /settings/notifications/available-ha-services``.
 *   The endpoint returns 409 when HA is unreachable or unconfigured,
 *   in which case the form falls back to a free-text entry and shows
 *   an inline hint.
 * * The default ``min_severity`` is ``critical`` per FR-017.
 * * The ``enabled`` toggle defaults on — most admins save the sink
 *   intending to receive alerts immediately.
 * * The stored endpoint value is the bare notify-service suffix
 *   (``mobile_app_pixel9``), never prefixed with ``notify.``. The
 *   backend strips the prefix on ingest, but this form also passes
 *   the bare form through to avoid confusing the server logs.
 */
export default function HomeAssistantSinkForm({
  onSaved,
}: {
  onSaved?: () => void;
}) {
  const [name, setName] = useState<string>("");
  const [service, setService] = useState<string>("");
  const [services, setServices] = useState<string[]>([]);
  const [servicesLoaded, setServicesLoaded] = useState(false);
  const [fallbackText, setFallbackText] = useState(false);
  const [fallbackReason, setFallbackReason] = useState<string | null>(null);
  const [enabled, setEnabled] = useState<boolean>(true);
  const [minSeverity, setMinSeverity] = useState<AlertSeverity>("critical");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetchAvailableHaServices();
        if (cancelled) return;
        if (res.ok) {
          setServices(res.services);
          if (res.services.length > 0) {
            setService(res.services[0]!);
          }
          setFallbackText(res.services.length === 0);
          if (res.services.length === 0) {
            setFallbackReason(
              "Home Assistant returned no notify.* services — enter the service name manually.",
            );
          }
        } else {
          setFallbackText(true);
          setFallbackReason(
            res.detail ??
              "Home Assistant is unreachable — enter the service name manually, e.g. mobile_app_pixel9",
          );
        }
      } catch (exc) {
        if (cancelled) return;
        setFallbackText(true);
        setFallbackReason(
          exc instanceof Error
            ? `Service lookup failed: ${exc.message}`
            : "Service lookup failed",
        );
      } finally {
        if (!cancelled) {
          setServicesLoaded(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function canonicalService(raw: string): string {
    const s = raw.trim();
    return s.startsWith("notify.") ? s.slice("notify.".length) : s;
  }

  async function handleSave() {
    setError(null);
    setSuccess(null);
    const endpoint = canonicalService(service);
    if (!name.trim() || !endpoint) {
      setError("Name and service are required.");
      return;
    }
    setSaving(true);
    try {
      await createNotificationSink({
        type: "home_assistant",
        name: name.trim(),
        enabled,
        endpoint,
        min_severity: minSeverity,
      });
      setSuccess(`Saved HA sink → notify.${endpoint}`);
      setName("");
      onSaved?.();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section
      className="rounded-lg border border-gray-200 bg-white p-4"
      data-testid="ha-sink-form"
    >
      <h2 className="mb-3 text-lg font-semibold text-gray-800">
        Home Assistant push notifications
      </h2>
      <p className="mb-3 text-xs text-gray-600">
        Forwards advisor alerts to a Home Assistant{" "}
        <code className="rounded bg-gray-100 px-1">notify.*</code> service
        (e.g. the mobile companion app on your phone). Requires a configured
        HA connection.
      </p>

      {error ? (
        <div className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700">
          {error}
        </div>
      ) : null}
      {success ? (
        <div className="mb-3 rounded bg-green-50 p-2 text-sm text-green-800">
          {success}
        </div>
      ) : null}

      <div className="space-y-3">
        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold uppercase text-gray-500">
            Name
          </span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Phone (HA push)"
            aria-label="Name"
            className="w-full rounded border border-gray-300 px-2 py-1"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold uppercase text-gray-500">
            Notify service
          </span>
          {servicesLoaded && !fallbackText ? (
            <select
              value={service}
              onChange={(e) => setService(e.target.value)}
              aria-label="Notify service"
              data-testid="ha-service-select"
              className="w-full rounded border border-gray-300 px-2 py-1"
            >
              {services.map((s) => (
                <option key={s} value={s}>
                  notify.{s}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={service}
              onChange={(e) => setService(e.target.value)}
              placeholder="mobile_app_pixel9"
              aria-label="Notify service"
              data-testid="ha-service-text"
              className="w-full rounded border border-gray-300 px-2 py-1 font-mono"
            />
          )}
          {fallbackText && fallbackReason ? (
            <span
              className="mt-1 block text-xs text-amber-700"
              data-testid="ha-service-fallback-reason"
            >
              {fallbackReason}
            </span>
          ) : null}
        </label>

        <div className="flex items-center gap-4">
          <label className="flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              aria-label="Enabled"
            />
            <span>Enabled</span>
          </label>

          <label className="flex items-center gap-1 text-sm">
            <span className="text-xs uppercase text-gray-500">Min severity</span>
            <select
              value={minSeverity}
              onChange={(e) => setMinSeverity(e.target.value as AlertSeverity)}
              aria-label="Min severity"
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
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </section>
  );
}
