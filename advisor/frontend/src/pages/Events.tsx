import { useEffect, useState } from "react";
import type { EventsResponse, NetworkEvent } from "../types";

const EVENT_BADGE: Record<string, string> = {
  "new-device": "bg-green-100 text-green-800",
  "back-online": "bg-green-100 text-green-800",
  offline: "bg-red-100 text-red-800",
  "scan-error": "bg-yellow-100 text-yellow-800",
};

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function EventRow({ event }: { event: NetworkEvent }) {
  const badgeClass = EVENT_BADGE[event.event_type] ?? "bg-gray-100 text-gray-700";
  const deviceLabel = event.device
    ? `${event.device.hostname ?? event.device.mac_address} (${event.device.ip_address})`
    : "—";

  return (
    <tr className="border-b border-gray-100 hover:bg-gray-50">
      <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-500">
        {formatTs(event.timestamp)}
      </td>
      <td className="px-4 py-2 whitespace-nowrap">
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${badgeClass}`}>
          {event.event_type}
        </span>
      </td>
      <td className="px-4 py-2 text-sm">{deviceLabel}</td>
      <td className="px-4 py-2 text-xs text-gray-400 font-mono max-w-xs truncate">
        {event.details ? JSON.stringify(event.details) : ""}
      </td>
    </tr>
  );
}

const PAGE_SIZE = 100;

export function Events() {
  const [data, setData] = useState<EventsResponse | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function fetchEvents(off: number) {
    setLoading(true);
    try {
      const res = await fetch(`/api/events?limit=${PAGE_SIZE}&offset=${off}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: EventsResponse = await res.json();
      setData(json);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchEvents(offset);
  }, [offset]);

  const total = data?.total ?? 0;
  const pageCount = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Event History</h1>
          {data && (
            <p className="text-sm text-gray-500 mt-1">{total} event{total !== 1 ? "s" : ""} (30-day retention)</p>
          )}
        </div>
        <button
          onClick={() => fetchEvents(offset)}
          className="px-3 py-1.5 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded text-red-700 text-sm mb-4">
          Failed to load events: {error}
        </div>
      )}

      <div className="overflow-x-auto rounded border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              {["Timestamp", "Event", "Device", "Details"].map((h) => (
                <th
                  key={h}
                  className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white">
            {loading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i}>
                  <td colSpan={4} className="px-4 py-2">
                    <div className="h-5 bg-gray-100 rounded animate-pulse" />
                  </td>
                </tr>
              ))
            ) : data?.events.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                  No events recorded yet
                </td>
              </tr>
            ) : (
              data?.events.map((ev) => <EventRow key={ev.id} event={ev} />)
            )}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className="mt-4 flex items-center gap-3 text-sm">
          <button
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            disabled={offset === 0}
            className="px-3 py-1 border rounded disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-gray-500">
            Page {currentPage} of {pageCount}
          </span>
          <button
            onClick={() => setOffset(offset + PAGE_SIZE)}
            disabled={currentPage >= pageCount}
            className="px-3 py-1 border rounded disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
