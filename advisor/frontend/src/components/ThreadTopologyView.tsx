import type {
  ThreadBorderRouter,
  ThreadDevice,
  ThreadTopologyResponse,
} from "../types";

interface ThreadTopologyViewProps {
  data: ThreadTopologyResponse | null;
}

function OnlinePill({ online }: { online: boolean }) {
  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-xs font-semibold ${
        online
          ? "border-green-200 bg-green-100 text-green-800"
          : "border-red-200 bg-red-100 text-red-800"
      }`}
    >
      {online ? "online" : "offline"}
    </span>
  );
}

function OnlineDot({ online }: { online: boolean }) {
  return (
    <span
      aria-label={online ? "online" : "offline"}
      className={`inline-block h-2 w-2 rounded-full ${
        online ? "bg-green-500" : "bg-red-500"
      }`}
    />
  );
}

function DeviceRow({
  device,
  isOrphanBadge,
}: {
  device: ThreadDevice;
  isOrphanBadge: boolean;
}) {
  return (
    <li className="flex items-center gap-2 py-1 text-sm">
      <OnlineDot online={device.online} />
      <span className="text-gray-800">{device.friendly_name}</span>
      {isOrphanBadge ? (
        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-semibold text-amber-800">
          orphan
        </span>
      ) : null}
      <span className="ml-auto font-mono text-xs text-gray-400">
        {device.ha_device_id}
      </span>
    </li>
  );
}

function BorderRouterCard({
  router,
  devices,
}: {
  router: ThreadBorderRouter;
  devices: ThreadDevice[];
}) {
  const attached = devices.filter(
    (d) => d.parent_border_router_id === router.ha_device_id,
  );
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-base font-bold text-gray-800">
            {router.friendly_name}
          </div>
          {router.model ? (
            <div className="text-xs text-gray-500">{router.model}</div>
          ) : null}
        </div>
        <OnlinePill online={router.online} />
      </div>

      {attached.length > 0 ? (
        <ul className="mt-3 divide-y divide-gray-100 border-t border-gray-100 pt-2">
          {attached.map((d) => (
            <DeviceRow
              key={d.ha_device_id}
              device={d}
              isOrphanBadge={
                d.parent_border_router_id !== router.ha_device_id
              }
            />
          ))}
        </ul>
      ) : (
        <div className="mt-3 border-t border-gray-100 pt-2 text-xs text-gray-400">
          No attached devices.
        </div>
      )}

      <div className="mt-3 text-xs text-gray-500">
        {router.attached_device_count} attached devices
      </div>
    </div>
  );
}

export default function ThreadTopologyView({ data }: ThreadTopologyViewProps) {
  if (!data) {
    return (
      <div className="space-y-2">
        {[...Array(2)].map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded bg-gray-100" />
        ))}
      </div>
    );
  }

  if (data.empty_reason === "no_thread_integration_data") {
    return (
      <div
        data-testid="thread-empty-state"
        className="rounded border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600"
      >
        <div className="font-semibold text-gray-700">
          No Thread data exposed by Home Assistant.
        </div>
        <div className="mt-1 text-xs text-gray-500">
          The Thread integration isn&apos;t configured, or your HA instance
          doesn&apos;t support it.
        </div>
      </div>
    );
  }

  const orphans = data.devices.filter(
    (d) => d.parent_border_router_id === null,
  );

  return (
    <div className="space-y-4">
      {data.border_routers.length === 0 && data.devices.length === 0 ? (
        <div className="rounded border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600">
          No Thread devices have been polled yet.
        </div>
      ) : null}

      {data.border_routers.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2">
          {data.border_routers.map((r) => (
            <BorderRouterCard
              key={r.ha_device_id}
              router={r}
              devices={data.devices}
            />
          ))}
        </div>
      ) : null}

      {orphans.length > 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="font-semibold text-amber-800">Orphaned</span>
            <span className="rounded bg-amber-200 px-1.5 py-0.5 text-xs font-semibold text-amber-900">
              {orphans.length}
            </span>
          </div>
          <ul className="divide-y divide-amber-100">
            {orphans.map((d) => (
              <DeviceRow key={d.ha_device_id} device={d} isOrphanBadge />
            ))}
          </ul>
          <div className="mt-2 text-xs text-amber-700">
            These devices have no current parent border router.
            {orphans.some((d) => d.last_seen_parent_id) ? (
              <> Last-known parent shown in tooltips.</>
            ) : null}
          </div>
        </div>
      ) : null}

      {data.polled_at ? (
        <div className="text-xs text-gray-400">
          Last refreshed: {new Date(data.polled_at).toLocaleString()}
        </div>
      ) : null}
    </div>
  );
}
