import { useEffect, useState } from "react";
import type { HAConnection, HAConnectionStatus } from "../types";
import {
  deleteHomeAssistantConnection,
  getHomeAssistantConnection,
  testHomeAssistantConnection,
  upsertHomeAssistantConnection,
} from "../services/homeAssistant";

type StatusClass = HAConnectionStatus | "invalid_url";

interface StatusResult {
  status: StatusClass;
  detail: string | null;
}

function statusPillClasses(status: StatusClass): string {
  switch (status) {
    case "ok":
      return "bg-green-100 text-green-800 border-green-200";
    case "auth_failure":
      return "bg-red-100 text-red-800 border-red-200";
    case "unreachable":
    case "unexpected_payload":
    case "invalid_url":
      return "bg-amber-100 text-amber-800 border-amber-200";
    case "not_configured":
    default:
      return "bg-gray-100 text-gray-700 border-gray-200";
  }
}

function statusLabel(status: StatusClass): string {
  switch (status) {
    case "ok":
      return "Connection OK";
    case "auth_failure":
      return "Authentication failed";
    case "unreachable":
      return "Home Assistant unreachable";
    case "unexpected_payload":
      return "Unexpected response";
    case "invalid_url":
      return "Invalid URL";
    case "not_configured":
      return "Not configured";
  }
}

function isValidUrl(url: string): boolean {
  return url.startsWith("http://") || url.startsWith("https://");
}

export default function HAConnectionForm() {
  const [connection, setConnection] = useState<HAConnection | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [baseUrl, setBaseUrl] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [replacingToken, setReplacingToken] = useState(false);

  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusResult, setStatusResult] = useState<StatusResult | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [removing, setRemoving] = useState(false);

  async function reload() {
    setLoading(true);
    try {
      const conn = await getHomeAssistantConnection();
      setConnection(conn);
      setBaseUrl(conn.base_url ?? "");
      setAccessToken("");
      setReplacingToken(false);
      setLoadError(null);
      if (conn.configured) {
        setStatusResult({ status: conn.status, detail: conn.last_error });
      } else {
        setStatusResult(null);
      }
    } catch (exc) {
      setLoadError(exc instanceof Error ? exc.message : "load failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  const tokenEditable = !connection?.configured || replacingToken;

  function handleReplaceToken() {
    setReplacingToken(true);
    setAccessToken("");
  }

  function handleCancelReplace() {
    setReplacingToken(false);
    setAccessToken("");
  }

  function validateInputs(): string | null {
    if (!isValidUrl(baseUrl)) {
      return "Base URL must start with http:// or https://";
    }
    if (tokenEditable && accessToken.trim() === "") {
      return "Access token is required";
    }
    return null;
  }

  async function handleTest() {
    const validation = validateInputs();
    if (validation) {
      setStatusResult({ status: "invalid_url", detail: validation });
      return;
    }
    setTesting(true);
    setStatusResult(null);
    try {
      const result = await testHomeAssistantConnection({
        base_url: baseUrl,
        access_token: accessToken,
      });
      setStatusResult({ status: result.status, detail: result.last_error });
    } catch (exc) {
      const err = exc as { status?: StatusClass; detail?: string; message?: string };
      setStatusResult({
        status: err.status ?? "unreachable",
        detail: err.detail ?? err.message ?? "test failed",
      });
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    const validation = validateInputs();
    if (validation) {
      setStatusResult({ status: "invalid_url", detail: validation });
      return;
    }
    setSaving(true);
    setStatusResult(null);
    try {
      const result = await upsertHomeAssistantConnection({
        base_url: baseUrl,
        access_token: accessToken,
      });
      setConnection(result);
      setBaseUrl(result.base_url ?? "");
      setAccessToken("");
      setReplacingToken(false);
      setStatusResult({ status: result.status, detail: result.last_error });
    } catch (exc) {
      const err = exc as { status?: StatusClass; detail?: string; message?: string };
      setStatusResult({
        status: err.status ?? "unreachable",
        detail: err.detail ?? err.message ?? "save failed",
      });
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove() {
    setRemoving(true);
    try {
      await deleteHomeAssistantConnection();
      setConfirmRemove(false);
      await reload();
    } catch (exc) {
      const err = exc as { detail?: string; message?: string };
      setStatusResult({
        status: "unreachable",
        detail: err.detail ?? err.message ?? "remove failed",
      });
    } finally {
      setRemoving(false);
    }
  }

  if (loading) {
    return (
      <section className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
        Loading Home Assistant connection...
      </section>
    );
  }

  if (loadError) {
    return (
      <section className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-700">
        Failed to load Home Assistant connection: {loadError}
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4">
      <h2 className="mb-3 text-lg font-semibold text-gray-800">
        Home Assistant connection
      </h2>

      <div className="space-y-3">
        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold uppercase text-gray-500">
            Base URL
          </span>
          <input
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://homeassistant.local:8123"
            className="w-full rounded border border-gray-300 px-2 py-1 font-mono"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-xs font-semibold uppercase text-gray-500">
            Long-lived access token
          </span>
          {connection?.configured && !replacingToken ? (
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={connection.token_masked ?? ""}
                disabled
                className="w-full rounded border border-gray-300 bg-gray-50 px-2 py-1 font-mono text-gray-500"
              />
              <button
                type="button"
                onClick={handleReplaceToken}
                className="whitespace-nowrap rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-100"
              >
                Replace token
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <input
                type="password"
                value={accessToken}
                onChange={(e) => setAccessToken(e.target.value)}
                placeholder="llat_..."
                className="w-full rounded border border-gray-300 px-2 py-1 font-mono"
              />
              {connection?.configured && replacingToken ? (
                <button
                  type="button"
                  onClick={handleCancelReplace}
                  className="whitespace-nowrap rounded border border-gray-300 px-2 py-1 text-xs hover:bg-gray-100"
                >
                  Cancel
                </button>
              ) : null}
            </div>
          )}
        </label>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleTest}
            disabled={testing || saving}
            className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-100 disabled:opacity-50"
          >
            {testing ? "Testing..." : "Test Connection"}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || testing}
            className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white disabled:bg-gray-300"
          >
            {saving ? "Saving..." : connection?.configured ? "Update" : "Save"}
          </button>
          {connection?.configured ? (
            <button
              type="button"
              onClick={() => setConfirmRemove(true)}
              className="rounded border border-red-300 px-3 py-1 text-sm text-red-700 hover:bg-red-50"
            >
              Remove
            </button>
          ) : null}
        </div>

        {statusResult ? (
          <div
            className={`rounded border px-3 py-2 text-sm ${statusPillClasses(
              statusResult.status,
            )}`}
          >
            <div className="font-semibold">{statusLabel(statusResult.status)}</div>
            {statusResult.detail ? (
              <div className="mt-1 text-xs">{statusResult.detail}</div>
            ) : null}
          </div>
        ) : null}

        {connection?.configured && connection.last_success_at ? (
          <div className="mt-2 border-t border-gray-100 pt-2 text-xs text-gray-500">
            Last successful poll:{" "}
            {new Date(connection.last_success_at).toLocaleString()}
          </div>
        ) : null}
      </div>

      {confirmRemove ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-lg">
            <h3 className="text-lg font-semibold text-gray-800">
              Remove Home Assistant connection?
            </h3>
            <p className="mt-2 text-sm text-gray-600">
              The advisor will stop polling Home Assistant. Existing HA-sourced
              inventory rows will remain but stop updating. This action cannot be
              undone — you'll need to re-enter the access token to reconnect.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmRemove(false)}
                disabled={removing}
                className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-100"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRemove}
                disabled={removing}
                className="rounded bg-red-600 px-3 py-1 text-sm font-medium text-white disabled:bg-gray-300"
              >
                {removing ? "Removing..." : "Remove"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
