import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";
import type { HAEntitiesResponse, HAEntity } from "../types";

interface HAEntityTableProps {
  response: HAEntitiesResponse | null;
}

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diffMs = Date.now() - then;
  const diffSec = Math.round(diffMs / 1000);
  if (diffSec < 0) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  return new Date(iso).toLocaleDateString();
}

function connectionStatusMessage(status: string): string {
  switch (status) {
    case "auth_failure":
      return "Authentication to Home Assistant failed.";
    case "unreachable":
      return "Home Assistant is currently unreachable.";
    case "unexpected_payload":
      return "Home Assistant returned an unexpected response.";
    case "not_configured":
      return "Home Assistant is not configured.";
    case "ok":
    default:
      return "";
  }
}

export default function HAEntityTable({ response }: HAEntityTableProps) {
  const entities: HAEntity[] = response?.entities ?? [];
  const [sorting, setSorting] = useState<SortingState>([]);
  const [search, setSearch] = useState("");
  const [selectedDomains, setSelectedDomains] = useState<Set<string>>(new Set());

  const allDomains = useMemo(() => {
    const set = new Set<string>();
    for (const ent of entities) set.add(ent.domain);
    return Array.from(set).sort();
  }, [entities]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return entities.filter((ent) => {
      if (selectedDomains.size > 0 && !selectedDomains.has(ent.domain)) {
        return false;
      }
      if (q) {
        return (
          ent.friendly_name.toLowerCase().includes(q) ||
          ent.entity_id.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [entities, search, selectedDomains]);

  function toggleDomain(domain: string) {
    setSelectedDomains((prev) => {
      const next = new Set(prev);
      if (next.has(domain)) next.delete(domain);
      else next.add(domain);
      return next;
    });
  }

  const columns: ColumnDef<HAEntity>[] = [
    {
      accessorKey: "friendly_name",
      header: "Friendly Name",
      cell: ({ row }) => (
        <div>
          <div className="font-medium text-gray-800">
            {row.original.friendly_name}
          </div>
          <div className="font-mono text-xs text-gray-400">
            {row.original.entity_id}
          </div>
        </div>
      ),
    },
    {
      accessorKey: "domain",
      header: "Domain",
      cell: ({ getValue }) => (
        <span className="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs text-gray-700">
          {getValue() as string}
        </span>
      ),
    },
    {
      accessorKey: "state",
      header: "State",
      cell: ({ getValue }) => (
        <span className="font-mono text-sm text-gray-700">
          {getValue() as string}
        </span>
      ),
    },
    {
      accessorKey: "last_changed",
      header: "Last Changed",
      cell: ({ getValue }) => {
        const iso = getValue() as string;
        return (
          <span
            className="text-xs text-gray-500"
            title={new Date(iso).toLocaleString()}
          >
            {formatRelative(iso)}
          </span>
        );
      },
    },
  ];

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const stale = response?.stale === true;
  const connStatus = response?.connection_status ?? "not_configured";
  const staleMsg = connectionStatusMessage(connStatus);

  return (
    <div>
      {stale ? (
        <div className="mb-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <div className="font-semibold">Showing cached snapshot</div>
          <div className="mt-0.5 text-xs">
            {staleMsg || "Home Assistant poll is stale."}
            {response?.polled_at ? (
              <>
                {" "}
                Last polled{" "}
                <span className="font-mono">
                  {new Date(response.polled_at).toLocaleString()}
                </span>
                .
              </>
            ) : null}
          </div>
        </div>
      ) : null}

      {allDomains.length > 0 ? (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase text-gray-500">Domain:</span>
          {allDomains.map((domain) => {
            const active = selectedDomains.has(domain);
            return (
              <button
                key={domain}
                type="button"
                onClick={() => toggleDomain(domain)}
                className={`rounded-full border px-2.5 py-0.5 font-mono text-xs ${
                  active
                    ? "border-blue-300 bg-blue-100 text-blue-800"
                    : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                {domain}
              </button>
            );
          })}
          {selectedDomains.size > 0 ? (
            <button
              type="button"
              onClick={() => setSelectedDomains(new Set())}
              className="text-xs text-blue-600 hover:underline"
            >
              Clear
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="mb-3">
        <input
          type="text"
          placeholder="Search by friendly name or entity ID…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full max-w-sm rounded border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>

      <div className="overflow-x-auto rounded border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className={`px-4 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500 select-none ${
                      header.column.getCanSort()
                        ? "cursor-pointer hover:bg-gray-100"
                        : ""
                    }`}
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === "asc" && " ↑"}
                    {header.column.getIsSorted() === "desc" && " ↓"}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="hover:bg-gray-50">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="whitespace-nowrap px-4 py-2">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-8 text-center text-sm text-gray-400"
                >
                  No Home Assistant entities match the current filter
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
