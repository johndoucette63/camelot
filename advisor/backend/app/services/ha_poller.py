"""Background Home Assistant poller (feature 016, US-1).

Runs as a third async background task alongside ``health_checker`` and
``rule_engine``. Every cycle:

1. Loads the singleton ``home_assistant_connections`` row (id=1).
2. If ``base_url IS NULL`` sleeps and continues (not configured -> no-op).
3. Calls ``ha_client.states(conn)``. On failure records the error class
   (``auth_failure`` / ``unreachable`` / ``unexpected_payload``), commits,
   logs JSON, and continues to the next cycle.
4. On success filters entities per the curated allowlist (research R2).
5. Upserts the filtered entities into ``ha_entity_snapshots`` and prunes
   rows whose entity_id is no longer present.
6. Invokes the inventory merge to reconcile HA devices with the unified
   ``devices`` table.
7. Updates the connection row with ``last_success_at`` and clears the
   error columns.
8. Emits one structured JSON log line per cycle.

All failures are caught — the loop never crashes the process. Shutdown
is cooperative via ``asyncio.CancelledError``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from app.config import settings
from app.database import async_session
from app.models.ha_entity_snapshot import HAEntitySnapshot
from app.models.home_assistant_connection import HomeAssistantConnection
from app.models.thread_border_router import ThreadBorderRouter
from app.models.thread_device import ThreadDevice
from app.services import (
    ha_client,
    ha_inventory_merge,
    ha_ws_client,
    notification_retry_sweeper,
)
from app.services.ha_client import (
    HAAuthError,
    HAClientError,
    HAUnexpectedPayloadError,
    HAUnreachableError,
)
from app.services.ha_ws_client import HAWSError

logger = logging.getLogger(__name__)


# ── Entity-domain allowlist (research R2) ────────────────────────────────

_BINARY_SENSOR_DEVICE_CLASSES = {"connectivity", "problem", "running", "update"}
_SENSOR_DEVICE_CLASSES = {"signal_strength", "battery", "temperature", "humidity"}
_WHOLE_DOMAIN_ALLOW = {"device_tracker", "switch", "update"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_thread_integration(attrs: dict[str, Any]) -> bool:
    """True if HA reports this entity as part of the Thread integration.

    HA does not always expose ``integration`` on the entity state object,
    so this is a defensive check — Thread entities frequently carry extra
    Thread-specific attributes (rloc16, extended_address) but the single
    reliable signal is ``attributes.get("integration") == "thread"``.
    """
    return attrs.get("integration") == "thread"


def _entity_allowed(entity: dict[str, Any]) -> bool:
    """Return True if an HA state entry passes the R2 curated filter."""
    entity_id = entity.get("entity_id") or ""
    if "." not in entity_id:
        return False
    domain, _ = entity_id.split(".", 1)
    attrs = entity.get("attributes") or {}

    if _is_thread_integration(attrs):
        return True
    if domain in _WHOLE_DOMAIN_ALLOW:
        return True
    if domain == "binary_sensor":
        return attrs.get("device_class") in _BINARY_SENSOR_DEVICE_CLASSES
    if domain == "sensor":
        return attrs.get("device_class") in _SENSOR_DEVICE_CLASSES
    return False


def _parse_last_changed(raw: str | None) -> datetime:
    """Parse HA's ISO-8601 ``last_changed`` into a naive UTC datetime.

    The snapshot table stores timezone-aware columns, but the rest of the
    advisor normalises to naive UTC to match the existing convention in
    ``health_checker`` / ``rule_engine``. If HA sends a malformed value
    we fall back to "now" — the alternative is to drop the row, which
    would lose real state updates for the sake of a timestamp quirk.
    """
    if not raw:
        return _utcnow()
    try:
        # HA emits ``2026-04-17T14:03:12.123456+00:00``; ``fromisoformat``
        # handles the ``+00:00`` form natively on 3.11+.
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return _utcnow()
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


ENTITY_SYNTHETIC_PREFIX = "entity:"


def _snapshot_row(
    entity: dict[str, Any],
    polled_at: datetime,
    registry_map: dict[str, str],
) -> HAEntitySnapshot | None:
    """Build an ``HAEntitySnapshot`` from a raw HA states payload entry.

    ``ha_device_id`` is resolved via ``registry_map`` (built from HA's
    ``/api/template`` device_id() rendering in ``ha_client``). Entities
    not in the registry — helpers, manual templates, some integrations —
    get a synthetic id ``entity:<entity_id>`` so they still appear in the
    snapshot and dashboard. The inventory merge skips synthetic ids since
    they are not real physical devices.
    """
    entity_id = entity.get("entity_id")
    if not entity_id or "." not in entity_id:
        return None
    attrs = entity.get("attributes") or {}
    ha_device_id = registry_map.get(entity_id) or f"{ENTITY_SYNTHETIC_PREFIX}{entity_id}"

    domain, _ = entity_id.split(".", 1)
    friendly_name = attrs.get("friendly_name") or entity_id
    state = entity.get("state") or ""
    last_changed = _parse_last_changed(entity.get("last_changed"))

    return HAEntitySnapshot(
        entity_id=entity_id,
        ha_device_id=str(ha_device_id),
        domain=domain,
        friendly_name=str(friendly_name),
        state=str(state),
        last_changed=last_changed,
        attributes=dict(attrs),
        polled_at=polled_at,
    )


async def _load_connection(session) -> HomeAssistantConnection | None:
    """Fetch the singleton connection row (id=1)."""
    return await session.get(HomeAssistantConnection, 1)


async def _record_error(
    session, conn: HomeAssistantConnection, error: HAClientError
) -> None:
    """Persist the classified error on the connection row."""
    conn.last_error = error.error_class
    conn.last_error_at = _utcnow()
    await session.commit()
    logger.warning(
        "ha_poll_cycle",
        extra={
            "event": "ha_poll_cycle",
            "status": error.error_class,
            # "message" is a reserved LogRecord attribute — rename.
            "error_detail": str(error),
        },
    )


async def _upsert_snapshots(
    session, rows: list[HAEntitySnapshot]
) -> tuple[int, int]:
    """Upsert filtered snapshot rows; delete entities no longer present.

    Returns ``(upserted, deleted)``.
    """
    incoming_ids = {r.entity_id for r in rows}

    existing_rows = (
        (await session.execute(select(HAEntitySnapshot))).scalars().all()
    )
    existing_by_id = {r.entity_id: r for r in existing_rows}

    upserted = 0
    for row in rows:
        prev = existing_by_id.get(row.entity_id)
        if prev is None:
            session.add(row)
        else:
            prev.ha_device_id = row.ha_device_id
            prev.domain = row.domain
            prev.friendly_name = row.friendly_name
            prev.state = row.state
            prev.last_changed = row.last_changed
            prev.attributes = row.attributes
            prev.polled_at = row.polled_at
        upserted += 1

    stale_ids = [eid for eid in existing_by_id.keys() if eid not in incoming_ids]
    deleted = 0
    if stale_ids:
        result = await session.execute(
            delete(HAEntitySnapshot).where(HAEntitySnapshot.entity_id.in_(stale_ids))
        )
        deleted = result.rowcount or 0

    return upserted, deleted


# ── Thread topology refresh (R3 / US-2) ─────────────────────────────────


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    """Defensive bool coercion — HA payloads occasionally use strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "online", "1", "yes")
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _parse_thread_payload(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract (border_routers, devices) from HA's /api/config/thread/status.

    HA's Thread status blob has evolved across versions. As of the HA
    2024+ Thread integration the payload includes the following shapes —
    we look for the first one that yields usable data:

    * ``{"routers": [{...}]}`` — preferred shape with full router records.
    * ``{"border_routers": [{...}]}`` — alternate key used in some builds.
    * ``{"datasets": [{...}]}`` — operational dataset list (older shape).

    For each router, child devices may appear under:
    * ``router["children"]`` — preferred when HA surfaces the parentage.
    * top-level ``payload["devices"]`` — flat list with ``parent`` / ``parent_border_router_id`` fields.

    Keys for each router record we read:
    * ``ha_device_id`` / ``device_id`` / ``extended_address`` — identifier
    * ``friendly_name`` / ``name`` — display name
    * ``model`` / ``manufacturer`` — optional
    * ``online`` / ``state`` — boolean-ish online flag

    Keys for each device record:
    * ``ha_device_id`` / ``device_id`` / ``extended_address``
    * ``friendly_name`` / ``name``
    * ``parent_border_router_id`` / ``parent`` / ``parent_router_id``
    * ``online`` / ``state``

    This is intentionally permissive: on a live HA instance, the first
    parse assumption we stumble on may need tweaking. That's a quickstart
    validation step, not a correctness bug.
    """
    router_records: list[dict[str, Any]] = []

    raw_routers = (
        payload.get("routers")
        or payload.get("border_routers")
        or payload.get("datasets")
        or []
    )
    if not isinstance(raw_routers, list):
        raw_routers = []

    children_by_router: dict[str, list[dict[str, Any]]] = {}

    for raw in raw_routers:
        if not isinstance(raw, dict):
            continue
        router_id = (
            raw.get("ha_device_id")
            or raw.get("device_id")
            or raw.get("extended_address")
            or raw.get("id")
        )
        if not router_id:
            continue
        router_id = str(router_id)
        friendly_name = str(
            raw.get("friendly_name") or raw.get("name") or router_id
        )
        model = raw.get("model") or raw.get("manufacturer")
        online = _coerce_bool(raw.get("online", raw.get("state")))

        children = raw.get("children") or raw.get("devices") or []
        if isinstance(children, list):
            children_by_router[router_id] = [
                c for c in children if isinstance(c, dict)
            ]
        attached_count = len(children_by_router.get(router_id, []))

        router_records.append(
            {
                "ha_device_id": router_id,
                "friendly_name": friendly_name,
                "model": str(model) if model is not None else None,
                "online": online,
                "attached_device_count": attached_count,
            }
        )

    # Top-level device list (flat shape). When HA gives us both per-router
    # children and a flat list, the flat list wins because it's the shape
    # that carries explicit parent pointers.
    device_records: list[dict[str, Any]] = []
    flat_devices = payload.get("devices")
    if isinstance(flat_devices, list):
        for raw in flat_devices:
            if not isinstance(raw, dict):
                continue
            dev_id = (
                raw.get("ha_device_id")
                or raw.get("device_id")
                or raw.get("extended_address")
                or raw.get("id")
            )
            if not dev_id:
                continue
            parent = (
                raw.get("parent_border_router_id")
                or raw.get("parent_router_id")
                or raw.get("parent")
            )
            device_records.append(
                {
                    "ha_device_id": str(dev_id),
                    "friendly_name": str(
                        raw.get("friendly_name") or raw.get("name") or dev_id
                    ),
                    "parent_border_router_id": str(parent) if parent else None,
                    "online": _coerce_bool(raw.get("online", raw.get("state"))),
                }
            )
    else:
        # No flat list — derive devices from per-router children arrays.
        for router_id, children in children_by_router.items():
            for raw in children:
                dev_id = (
                    raw.get("ha_device_id")
                    or raw.get("device_id")
                    or raw.get("extended_address")
                    or raw.get("id")
                )
                if not dev_id:
                    continue
                explicit_parent = (
                    raw.get("parent_border_router_id")
                    or raw.get("parent_router_id")
                    or raw.get("parent")
                )
                parent = str(explicit_parent) if explicit_parent else router_id
                device_records.append(
                    {
                        "ha_device_id": str(dev_id),
                        "friendly_name": str(
                            raw.get("friendly_name") or raw.get("name") or dev_id
                        ),
                        "parent_border_router_id": parent,
                        "online": _coerce_bool(
                            raw.get("online", raw.get("state"))
                        ),
                    }
                )

    return router_records, device_records


async def _refresh_thread_tables(
    session, conn: HomeAssistantConnection, cycle_start: datetime
) -> tuple[int, int]:
    """Refresh ``thread_border_routers`` + ``thread_devices`` from HA.

    Returns ``(border_routers, devices)`` counts after the upsert, or
    ``(0, 0)`` on empty payload / parse error.

    Failure semantics: this helper must not raise out of ``run_cycle``.
    Callers wrap it in a try/except and log on unexpected errors.
    """
    # Prefer the WebSocket path — HA's REST /api/config/thread/status
    # returns 404 on current versions, so this is the only way to read
    # live Thread topology. Fall back to REST only if WS fails entirely.
    router_records: list[dict[str, Any]] = []
    device_records: list[dict[str, Any]] = []
    source = "ws"
    try:
        router_records = await _fetch_routers_via_ws(conn)
    except HAWSError as exc:
        logger.info(
            "thread_refresh.ws_failed",
            extra={
                "event": "thread_refresh.ws_failed",
                "error_class": exc.error_class,
                "error": str(exc)[:200],
            },
        )
        # REST fallback: older HA versions or WS disabled. Same semantics
        # as before — None means no Thread integration, populated dict
        # gets parsed into the router/device record shape.
        source = "rest"
        try:
            payload = await ha_client.thread_status(conn)
        except HAClientError as rest_exc:
            # Both paths failed — preserve current state, do not wipe tables.
            logger.warning(
                "thread_refresh.both_paths_failed",
                extra={
                    "event": "thread_refresh.both_paths_failed",
                    "ws_error": exc.error_class,
                    "rest_error": rest_exc.error_class,
                },
            )
            return 0, 0
        if payload is None:
            # REST reports no Thread integration. Mark all existing
            # routers offline (don't delete — the offline rule needs to
            # observe the online→offline transition) and clear devices.
            await session.execute(delete(ThreadDevice))
            await session.execute(
                ThreadBorderRouter.__table__.update().values(
                    online=False, last_refreshed_at=cycle_start
                )
            )
            logger.info(
                "thread_refresh",
                extra={
                    "event": "thread_refresh",
                    "border_routers": 0,
                    "devices": 0,
                    "source": "rest",
                    "status": "empty",
                },
            )
            return 0, 0
        try:
            router_records, device_records = _parse_thread_payload(payload)
        except Exception:  # noqa: BLE001 — parse defensiveness
            logger.warning(
                "thread_refresh.parse_failed",
                extra={
                    "event": "thread_refresh.parse_failed",
                    "status": "parse_error",
                    "source": "rest",
                },
            )
            return 0, 0

    incoming_router_ids = {r["ha_device_id"] for r in router_records}
    existing_routers = (
        (await session.execute(select(ThreadBorderRouter))).scalars().all()
    )
    routers_by_id = {r.ha_device_id: r for r in existing_routers}

    for rec in router_records:
        prev = routers_by_id.get(rec["ha_device_id"])
        if prev is None:
            session.add(
                ThreadBorderRouter(
                    ha_device_id=rec["ha_device_id"],
                    friendly_name=rec["friendly_name"],
                    model=rec["model"],
                    online=rec["online"],
                    attached_device_count=rec["attached_device_count"],
                    last_refreshed_at=cycle_start,
                )
            )
        else:
            prev.friendly_name = rec["friendly_name"]
            prev.model = rec["model"]
            prev.online = rec["online"]
            prev.attached_device_count = rec["attached_device_count"]
            prev.last_refreshed_at = cycle_start

    stale_router_ids = [
        rid for rid in routers_by_id.keys() if rid not in incoming_router_ids
    ]
    if stale_router_ids:
        # Mark stale routers OFFLINE rather than delete them. The
        # thread_border_router_offline rule watches for online→offline
        # transitions, so the row must persist in the table for the rule
        # to observe the state change on subsequent cycles.
        await session.execute(
            ThreadBorderRouter.__table__.update()
            .where(ThreadBorderRouter.ha_device_id.in_(stale_router_ids))
            .values(online=False, last_refreshed_at=cycle_start)
        )

    incoming_device_ids = {d["ha_device_id"] for d in device_records}
    existing_devices = (
        (await session.execute(select(ThreadDevice))).scalars().all()
    )
    devices_by_id = {d.ha_device_id: d for d in existing_devices}

    for rec in device_records:
        parent = rec["parent_border_router_id"]
        prev = devices_by_id.get(rec["ha_device_id"])
        if prev is None:
            session.add(
                ThreadDevice(
                    ha_device_id=rec["ha_device_id"],
                    friendly_name=rec["friendly_name"],
                    parent_border_router_id=parent,
                    online=rec["online"],
                    # Seed last_seen_parent_id from the first parent we see.
                    last_seen_parent_id=parent,
                    last_refreshed_at=cycle_start,
                )
            )
        else:
            prev.friendly_name = rec["friendly_name"]
            prev.parent_border_router_id = parent
            prev.online = rec["online"]
            # Preserve "last connected via X" across refreshes — only
            # advance last_seen_parent_id when we have a non-null parent.
            if parent is not None:
                prev.last_seen_parent_id = parent
            prev.last_refreshed_at = cycle_start

    stale_device_ids = [
        did for did in devices_by_id.keys() if did not in incoming_device_ids
    ]
    if stale_device_ids:
        await session.execute(
            delete(ThreadDevice).where(
                ThreadDevice.ha_device_id.in_(stale_device_ids)
            )
        )

    logger.info(
        "thread_refresh",
        extra={
            "event": "thread_refresh",
            "border_routers": len(router_records),
            "devices": len(device_records),
            "source": source,
            "status": "ok",
        },
    )
    return len(router_records), len(device_records)


def _looks_like_ipv4(s: str) -> bool:
    parts = s.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except (ValueError, TypeError):
        return False


def _router_from_ws(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Translate a WS ``router_discovered`` data payload into our router
    record shape. Returns ``None`` if the payload is missing an identity."""
    ha_device_id = (raw.get("extended_address") or raw.get("key") or "").strip()
    if not ha_device_id:
        return None
    vendor = (raw.get("vendor_name") or "").strip()
    model = (raw.get("model_name") or "").strip()
    if vendor and model:
        combined: str | None = f"{vendor} {model}"
    else:
        combined = vendor or model or None
    friendly = (
        raw.get("instance_name")
        or raw.get("server", "").rstrip(".")
        or ha_device_id
    )
    lan_ip = next(
        (a for a in (raw.get("addresses") or []) if _looks_like_ipv4(a)),
        None,
    )
    return {
        "ha_device_id": ha_device_id,
        "friendly_name": str(friendly),
        "model": combined,
        "online": True,  # mDNS-discovered this cycle = online
        # HA's WS API does not expose endpoint parentage, so we cannot
        # know how many Thread devices are attached to each border
        # router without talking to the OTBR directly. Leave at 0.
        "attached_device_count": 0,
        # Carried for logging / future inventory dedup. Not persisted on
        # ThreadBorderRouter (no column) but logged for diagnostics.
        "_lan_ipv4": lan_ip,
        "_network_name": raw.get("network_name"),
        "_extended_pan_id": raw.get("extended_pan_id"),
    }


async def _fetch_routers_via_ws(
    conn: HomeAssistantConnection,
) -> list[dict[str, Any]]:
    """Discover Thread border routers via HA's WebSocket API.

    Steps:
      1. ``thread/list_datasets`` to identify the preferred network's
         extended_pan_id (so we ignore border routers from neighbouring
         Thread networks that mDNS may surface — e.g. an Amazon Echo
         advertising its own network).
      2. ``thread/discover_routers`` subscription to collect all
         border routers HA sees on the LAN in a short mDNS window.

    Returns the list of router records filtered to the preferred network
    (or unfiltered if no dataset is marked preferred). Raises
    ``HAWSError`` subclasses on failure so the caller can decide whether
    to fall back to the REST path.
    """
    datasets = await ha_ws_client.list_thread_datasets(conn)
    preferred_epanid: str | None = None
    for d in datasets:
        if d.get("preferred"):
            preferred_epanid = d.get("extended_pan_id")
            break

    discovered = await ha_ws_client.discover_routers(conn, duration_seconds=3.5)

    # Dedupe by extended_address — HA can emit a router twice during the
    # discovery window (initial cached result + live mDNS hit).
    seen: dict[str, dict[str, Any]] = {}
    for raw in discovered:
        if preferred_epanid and raw.get("extended_pan_id") != preferred_epanid:
            continue
        rec = _router_from_ws(raw)
        if rec is None:
            continue
        # Keep the most recent entry per ha_device_id.
        seen[rec["ha_device_id"]] = rec

    logger.info(
        "thread_refresh.ws_discovered",
        extra={
            "event": "thread_refresh.ws_discovered",
            "total_events": len(discovered),
            "preferred_epanid": preferred_epanid,
            "unique_routers": len(seen),
        },
    )
    return list(seen.values())


# ── Cycle ────────────────────────────────────────────────────────────────


async def run_cycle() -> dict[str, Any]:
    """Run exactly one poll cycle. Safe to call from tests."""
    cycle_start_monotonic = time.monotonic()
    cycle_start = _utcnow()
    stats: dict[str, Any] = {
        "event": "ha_poll_cycle",
        "status": "skipped",
        "entities": 0,
        "upserted": 0,
        "deleted": 0,
        "duration_ms": 0,
    }

    async with async_session() as session:
        conn = await _load_connection(session)
        if conn is None or conn.base_url is None:
            stats["status"] = "not_configured"
            stats["duration_ms"] = int((time.monotonic() - cycle_start_monotonic) * 1000)
            return stats

        try:
            raw_entities = await ha_client.states(conn)
        except HAClientError as exc:
            await _record_error(session, conn, exc)
            stats["status"] = exc.error_class
            stats["duration_ms"] = int((time.monotonic() - cycle_start_monotonic) * 1000)
            return stats

        # Resolve entity_id -> device_id once per cycle via the template
        # API. HA's /api/states doesn't include device_id in attributes;
        # see ha_client.device_registry_map for why. On failure (older HA
        # versions or template API disabled) we fall back to synthetic
        # ids so the cycle still produces snapshots.
        try:
            registry_map = await ha_client.device_registry_map(conn)
        except HAClientError as exc:
            logger.warning(
                "ha_poll_cycle.registry_unavailable",
                extra={
                    "event": "ha_poll_cycle.registry_unavailable",
                    "error_class": exc.error_class,
                },
            )
            registry_map = {}

        filtered = [e for e in raw_entities if _entity_allowed(e)]
        rows: list[HAEntitySnapshot] = []
        for entity in filtered:
            row = _snapshot_row(entity, cycle_start, registry_map)
            if row is not None:
                rows.append(row)

        upserted, deleted = await _upsert_snapshots(session, rows)

        try:
            await ha_inventory_merge.merge_ha_devices(session, rows, conn)
        except Exception:  # noqa: BLE001 — merge errors must not crash the loop
            logger.exception(
                "ha_poll_cycle.merge_failed",
                extra={"event": "ha_poll_cycle.merge_failed"},
            )

        # Thread topology refresh (US-2). Runs after snapshot upsert so the
        # Thread tables land in the same commit as the entity snapshot. An
        # HAClientError here records the error class on the connection row
        # and short-circuits; any other exception is logged but swallowed
        # so it never crashes the poll loop.
        try:
            await _refresh_thread_tables(session, conn, cycle_start)
        except HAClientError as exc:
            await _record_error(session, conn, exc)
            stats["status"] = exc.error_class
            stats["duration_ms"] = int(
                (time.monotonic() - cycle_start_monotonic) * 1000
            )
            return stats
        except Exception:  # noqa: BLE001
            logger.exception(
                "thread_refresh.failed",
                extra={"event": "thread_refresh.failed"},
            )

        conn.last_success_at = cycle_start
        conn.last_error = None
        conn.last_error_at = None
        await session.commit()

        # Notification retry sweeper (feature 016 / US-3). Runs after
        # the connection state is committed so a failed sweep never
        # rolls back a successful poll. Failures inside the sweeper
        # are caught internally — this try/except is a final
        # belt-and-suspenders guard so a bug there never crashes the
        # poll loop.
        try:
            await notification_retry_sweeper.sweep(session)
        except Exception:  # noqa: BLE001
            logger.exception(
                "ha_poll_cycle.retry_sweep_failed",
                extra={"event": "ha_poll_cycle.retry_sweep_failed"},
            )

        duration_ms = int((time.monotonic() - cycle_start_monotonic) * 1000)
        stats.update(
            {
                "status": "ok",
                "entities": len(rows),
                "upserted": upserted,
                "deleted": deleted,
                "duration_ms": duration_ms,
            }
        )
        logger.info("ha_poll_cycle", extra=stats)
        return stats


# ── Loop entry point ─────────────────────────────────────────────────────


async def run_ha_poller() -> None:
    """Long-running background task. Call once from FastAPI lifespan."""
    await asyncio.sleep(2)

    while True:
        try:
            await run_cycle()
        except asyncio.CancelledError:
            logger.info("HA poller shutting down")
            raise
        except Exception:  # noqa: BLE001
            logger.exception(
                "ha_poll_cycle.failed",
                extra={"event": "ha_poll_cycle.failed"},
            )

        await asyncio.sleep(settings.ha_poll_interval_seconds)
