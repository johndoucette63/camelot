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

function haConnectivityClasses(type: string): string {
  switch (type) {
    case "wifi":
      return "border-blue-200 bg-blue-50 text-blue-700";
    case "ethernet":
      return "border-slate-200 bg-slate-50 text-slate-700";
    case "thread":
      return "border-purple-200 bg-purple-50 text-purple-700";
    case "zigbee":
      return "border-amber-200 bg-amber-50 text-amber-700";
    case "other":
    default:
      return "border-gray-200 bg-gray-50 text-gray-700";
  }
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
      cell: ({ getValue }) => {
        const mac = getValue() as string | null;
        return mac ? (
          <span className="font-mono text-sm">{mac}</span>
        ) : (
          <span className="text-gray-400">—</span>
        );
      },
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
      id: "ha_connectivity",
      header: "HA",
      accessorFn: (row) => row.ha_connectivity_type ?? "",
      cell: ({ row }) => {
        const type = row.original.ha_connectivity_type;
        if (!type) return <span className="text-gray-400">—</span>;
        const style = haConnectivityClasses(type);
        return (
          <span
            className={`rounded-full border px-2 py-0.5 text-xs font-medium ${style}`}
          >
            {type}
          </span>
        );
      },
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
      cell: ({ row }) => {
        const disabled = !row.original.mac_address;
        return (
          <input
            type="checkbox"
            checked={row.original.monitor_offline}
            disabled={disabled}
            title={
              disabled
                ? "Offline monitoring requires a MAC address"
                : row.original.monitor_offline
                  ? "Offline monitoring enabled"
                  : "Offline monitoring disabled"
            }
            onChange={(e) => {
              e.stopPropagation();
              onToggleMonitor?.(row.original);
            }}
            onClick={(e) => e.stopPropagation()}
            className="h-4 w-4 cursor-pointer rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
          />
        );
      },
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      size: 70,
      cell: ({ row }) => {
        const disabled = !row.original.mac_address;
        return (
          <button
            title={disabled ? "Re-scan requires a MAC address" : "Re-scan this device"}
            disabled={disabled}
            onClick={(e) => {
              e.stopPropagation();
              if (!disabled) onRescan?.(row.original);
            }}
            className="rounded border border-gray-200 px-2 py-0.5 text-xs text-gray-500 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-gray-500"
          >
            Re-scan
          </button>
        );
      },
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
