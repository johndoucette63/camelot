import type { ContainerState, ContainerInfo } from "../types";

function ContainerRow({ container }: { container: ContainerInfo }) {
  const ports = Object.entries(container.ports)
    .map(([k, v]) => (v ? `${k} → ${JSON.stringify(v)}` : k))
    .join(", ");

  return (
    <tr className="border-b border-gray-100 last:border-0">
      <td className="py-2 pr-4 pl-3 font-medium text-gray-800">{container.name}</td>
      <td className="py-2 pr-4 text-sm text-gray-500 truncate max-w-[200px]">{container.image}</td>
      <td className="py-2 pr-4">
        <span
          className={`inline-block px-2 py-0.5 text-xs rounded-full font-medium ${
            container.status === "running"
              ? "bg-green-100 text-green-700"
              : "bg-gray-100 text-gray-600"
          }`}
        >
          {container.status}
        </span>
      </td>
      <td className="py-2 pr-4 text-sm text-gray-500 font-mono">{ports || "—"}</td>
    </tr>
  );
}

function ContainerTable({ containers }: { containers: ContainerInfo[] }) {
  return (
    <div className="bg-white rounded border border-gray-200 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
            <th className="py-2 pr-4 pl-3">Name</th>
            <th className="py-2 pr-4">Image</th>
            <th className="py-2 pr-4">Status</th>
            <th className="py-2 pr-4">Ports</th>
          </tr>
        </thead>
        <tbody>
          {containers.map((c) => (
            <ContainerRow key={c.id} container={c} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface ContainerListProps {
  data: ContainerState;
}

export function ContainerList({ data }: ContainerListProps) {
  const { running, stopped, refreshed_at, socket_error } = data;
  const hasContainers = running.length > 0 || stopped.length > 0;

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-800 mb-3">
        Docker Containers
        <span className="text-sm font-normal text-gray-500 ml-2">HOLYGRAIL</span>
      </h2>

      {socket_error && (
        <div className="mb-3 px-4 py-2 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-800">
          Docker socket unavailable — showing last known state
          {refreshed_at && (
            <span className="text-yellow-600 ml-1">
              (as of {new Date(refreshed_at).toLocaleTimeString()})
            </span>
          )}
        </div>
      )}

      {!hasContainers && (
        <p className="text-sm text-gray-500 italic">No container data available yet.</p>
      )}

      {running.length > 0 && (
        <div className="mb-4">
          <h3 className="text-sm font-medium text-gray-600 mb-2">
            Running ({running.length})
          </h3>
          <ContainerTable containers={running} />
        </div>
      )}

      {stopped.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-600 mb-2">
            Stopped ({stopped.length})
          </h3>
          <ContainerTable containers={stopped} />
        </div>
      )}
    </div>
  );
}
