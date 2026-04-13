import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { useState } from "react";
import { StatusDot } from "./StatusDot";
import type { Device } from "../types";

interface DeviceTableProps {
  devices: Device[];
  onRowClick?: (device: Device) => void;
  onToggleMonitor?: (device: Device) => void;
  onRescan?: (device: Device) => void;
}


export function DeviceTable({ devices, onRowClick, onToggleMonitor, onRescan }: DeviceTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");

  const columns: ColumnDef<Device>[] = [
    {
      id: "status",
      header: "",
      cell: ({ row }) => <StatusDot isOnline={row.original.is_online} />,
      enableSorting: false,
      size: 32,
    },
    {
      accessorKey: "ip_address",
      header: "IP Address",
      cell: ({ getValue }) => (
        <span className="font-mono text-sm">{getValue() as string}</span>
      ),
    },
    {
      accessorKey: "hostname",
      header: "Hostname",
      cell: ({ getValue }) => (getValue() as string | null) ?? <span className="text-gray-400">—</span>,
    },
    {
      accessorKey: "mac_address",
      header: "MAC Address",
      cell: ({ getValue }) => (
        <span className="font-mono text-sm">{getValue() as string}</span>
      ),
    },
    {
      accessorKey: "vendor",
      header: "Vendor",
      cell: ({ getValue }) => (getValue() as string | null) ?? <span className="text-gray-400">—</span>,
    },
    {
      accessorKey: "os_family",
      header: "OS",
      cell: ({ getValue }) => (getValue() as string | null) ?? <span className="text-gray-400">—</span>,
    },
    {
      id: "role",
      header: "Role",
      accessorFn: (row) => row.annotation?.role ?? "—",
      cell: ({ row }) => {
        const role = row.original.annotation?.role ?? "—";
        const source = row.original.annotation?.classification_source;
        const isAuto = source && source !== "user";
        return (
          <span className="text-sm capitalize">
            {role}
            {isAuto && (
              <span className="ml-1 text-xs text-gray-400 font-normal">(auto)</span>
            )}
          </span>
        );
      },
    },
    {
      id: "tags",
      header: "Tags",
      enableSorting: false,
      accessorFn: (row) => (row.annotation?.tags ?? []).join(" "),
      cell: ({ row }) => {
        const tags = row.original.annotation?.tags ?? [];
        if (tags.length === 0) return <span className="text-gray-400">—</span>;
        return (
          <div className="flex flex-wrap gap-1">
            {tags.map((tag) => (
              <span
                key={tag}
                className="px-1.5 py-0.5 text-xs bg-gray-100 text-gray-600 rounded"
              >
                {tag}
              </span>
            ))}
          </div>
        );
      },
    },
    {
      id: "monitor_offline",
      header: "Monitor",
      enableSorting: false,
      size: 70,
      cell: ({ row }) => (
        <input
          type="checkbox"
          checked={row.original.monitor_offline}
          title={row.original.monitor_offline ? "Offline monitoring enabled" : "Offline monitoring disabled"}
          onChange={(e) => {
            e.stopPropagation();
            onToggleMonitor?.(row.original);
          }}
          onClick={(e) => e.stopPropagation()}
          className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
        />
      ),
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      size: 70,
      cell: ({ row }) => (
        <button
          title="Re-scan this device"
          onClick={(e) => {
            e.stopPropagation();
            onRescan?.(row.original);
          }}
          className="px-2 py-0.5 text-xs text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded border border-gray-200"
        >
          Re-scan
        </button>
      ),
    },
  ];

  const table = useReactTable({
    data: devices,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    globalFilterFn: (row, _columnId, filterValue: string) => {
      const q = filterValue.toLowerCase();
      return (
        (row.original.hostname?.toLowerCase().includes(q) ?? false) ||
        row.original.ip_address.toLowerCase().includes(q) ||
        (row.original.vendor?.toLowerCase().includes(q) ?? false) ||
        (row.original.annotation?.tags ?? []).some((t) => t.toLowerCase().includes(q)) ||
        (row.original.os_family?.toLowerCase().includes(q) ?? false) ||
        (row.original.mdns_name?.toLowerCase().includes(q) ?? false) ||
        (row.original.netbios_name?.toLowerCase().includes(q) ?? false) ||
        (row.original.ssdp_friendly_name?.toLowerCase().includes(q) ?? false)
      );
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <div>
      <div className="mb-3">
        <input
          type="text"
          placeholder="Filter by hostname, IP, vendor, or tag…"
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className="w-full max-w-sm px-3 py-1.5 border border-gray-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
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
                    className={`px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider select-none ${header.column.getCanSort() ? "cursor-pointer hover:bg-gray-100" : ""}`}
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
          <tbody className="bg-white divide-y divide-gray-100">
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => onRowClick?.(row.original)}
                className={`${onRowClick ? "cursor-pointer hover:bg-gray-50" : ""} ${row.original.is_known_device ? "bg-blue-50" : ""}`}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-4 py-2 whitespace-nowrap">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {table.getRowModel().rows.length === 0 && (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-8 text-center text-gray-400"
                >
                  No devices found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
