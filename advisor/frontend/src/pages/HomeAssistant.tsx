import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import HAEntityTable from "../components/HAEntityTable";
import ThreadTopologyView from "../components/ThreadTopologyView";
import {
  getHomeAssistantConnection,
  getHomeAssistantEntities,
  getThreadTopology,
} from "../services/homeAssistant";
import type {
  HAConnection,
  HAEntitiesResponse,
  HAConnectionStatus,
  ThreadTopologyResponse,
} from "../types";

const POLL_INTERVAL = 60_000;

function statusBadgeClasses(status: HAConnectionStatus): string {
  switch (status) {
    case "ok":
      return "bg-green-100 text-green-800 border-green-200";
    case "auth_failure":
      return "bg-red-100 text-red-800 border-red-200";
    case "unreachable":
    case "unexpected_payload":
      return "bg-amber-100 text-amber-800 border-amber-200";
    case "not_configured":
    default:
      return "bg-gray-100 text-gray-700 border-gray-200";
  }
}

function statusLabel(status: HAConnectionStatus): string {
  switch (status) {
    case "ok":
      return "Connected";
    case "auth_failure":
      return "Auth failure";
    case "unreachable":
      return "Unreachable";
    case "unexpected_payload":
      return "Unexpected payload";
    case "not_configured":
      return "Not configured";
  }
}

export default function HomeAssistant() {
  const [connection, setConnection] = useState<HAConnection | null>(null);
  const [entities, setEntities] = useState<HAEntitiesResponse | null>(null);
  const [thread, setThread] = useState<ThreadTopologyResponse | null>(null);
  const [connError, setConnError] = useState<string | null>(null);
  const [entityError, setEntityError] = useState<string | null>(null);
  const [threadError, setThreadError] = useState<string | null>(null);

  async function loadConnection() {
    try {
      setConnection(await getHomeAssistantConnection());
      setConnError(null);
    } catch (exc) {
      setConnError(exc instanceof Error ? exc.message : "connection load failed");
    }
  }

  async function loadEntities() {
    try {
      setEntities(await getHomeAssistantEntities());
      setEntityError(null);
    } catch (exc) {
      setEntityError(exc instanceof Error ? exc.message : "entity load failed");
    }
  }

  async function loadThread() {
    try {
      setThread(await getThreadTopology());
      setThreadError(null);
    } catch (exc) {
      setThreadError(exc instanceof Error ? exc.message : "thread load failed");
    }
  }

  useEffect(() => {
    void loadConnection();
    void loadEntities();
    void loadThread();
    const id = setInterval(() => {
      void loadConnection();
      void loadEntities();
      void loadThread();
    }, POLL_INTERVAL);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">Home Assistant</h1>
      </div>

      {/* Connection status card */}
      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <h2 className="mb-3 text-lg font-semibold text-gray-800">Connection</h2>
        {connError ? (
          <div className="rounded bg-red-50 p-2 text-sm text-red-700">
            Failed to load connection status: {connError}
          </div>
        ) : !connection ? (
          <div className="text-sm text-gray-500">Loading connection status...</div>
        ) : !connection.configured ? (
          <div className="rounded border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
            <p>Home Assistant is not yet configured.</p>
            <p className="mt-1">
              Configure your Home Assistant connection in{" "}
              <Link to="/settings" className="text-blue-600 hover:underline">
                Settings → Home Assistant
              </Link>
              .
            </p>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span
              className={`rounded border px-2.5 py-0.5 text-xs font-semibold ${statusBadgeClasses(
                connection.status,
              )}`}
            >
              {statusLabel(connection.status)}
            </span>
            <span className="font-mono text-xs text-gray-600">
              {connection.base_url}
            </span>
            {connection.last_success_at ? (
              <span className="text-xs text-gray-500">
                Last success:{" "}
                {new Date(connection.last_success_at).toLocaleString()}
              </span>
            ) : null}
            {connection.last_error ? (
              <div className="w-full text-xs text-red-600">
                {connection.last_error}
              </div>
            ) : null}
          </div>
        )}
      </section>

      {/* Entity snapshot table */}
      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <h2 className="mb-3 text-lg font-semibold text-gray-800">Entities</h2>
        {entityError ? (
          <div className="rounded bg-red-50 p-2 text-sm text-red-700">
            Failed to load entities: {entityError}
          </div>
        ) : !entities ? (
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-gray-100" />
            ))}
          </div>
        ) : entities.entities.length === 0 &&
          entities.connection_status === "not_configured" ? (
          <div className="rounded border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600">
            No entity data available — configure Home Assistant first.
          </div>
        ) : (
          <HAEntityTable response={entities} />
        )}
      </section>

      {/* Thread topology */}
      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <h2 className="mb-3 text-lg font-semibold text-gray-800">Thread</h2>
        {threadError ? (
          <div className="rounded bg-red-50 p-2 text-sm text-red-700">
            Failed to load Thread topology: {threadError}
          </div>
        ) : (
          <ThreadTopologyView data={thread} />
        )}
      </section>
    </div>
  );
}
