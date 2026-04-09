import { useEffect, useState } from "react";
import { DeviceTable } from "../components/DeviceTable";
import { DeviceAnnotationModal } from "../components/DeviceAnnotationModal";
import type { Device } from "../types";

export function Devices() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);

  async function fetchDevices() {
    try {
      const res = await fetch("/api/devices");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Device[] = await res.json();
      setDevices(data);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchDevices();
  }, []);

  const onlineCount = devices.filter((d) => d.is_online).length;

  function handleAnnotationSaved() {
    setSelectedDevice(null);
    fetchDevices();
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Device Inventory</h1>
          {!loading && (
            <p className="text-sm text-gray-500 mt-1">
              {devices.length} device{devices.length !== 1 ? "s" : ""},{" "}
              {onlineCount} online
            </p>
          )}
        </div>
        <button
          onClick={() => { setLoading(true); fetchDevices(); }}
          className="px-3 py-1.5 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50"
        >
          Refresh
        </button>
      </div>

      {loading && (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-10 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
          Failed to load devices: {error}
        </div>
      )}

      {!loading && !error && (
        <DeviceTable
          devices={devices}
          onRowClick={(device) => setSelectedDevice(device)}
        />
      )}

      {selectedDevice && (
        <DeviceAnnotationModal
          device={selectedDevice}
          onClose={() => setSelectedDevice(null)}
          onSaved={handleAnnotationSaved}
        />
      )}
    </div>
  );
}
