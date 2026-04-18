"""Unified-inventory merge for Home Assistant-known devices (feature 016).

Called at the end of every HA poll cycle with the filtered snapshot rows.
The function groups snapshots by ``ha_device_id`` and, for each group:

1. Derives a connectivity type from the entity mix (Thread / Zigbee /
   lan_wifi / other) — documented heuristic below.
2. Extracts a LAN MAC and IP when HA exposes them on the entity's
   attributes (many HA integrations do not, which is exactly why the
   ``devices.mac_address`` column was relaxed to nullable in the 016
   migration).
3. Matches an existing ``devices`` row by ``ha_device_id`` first, then
   MAC, then IP. A match attaches ``ha_device_id`` / ``ha_connectivity_type``
   / ``ha_last_seen_at`` to the existing row WITHOUT overwriting its
   scanner-provided ``mac_address`` / ``ip_address`` (FR-027 — scanner
   stays authoritative for LAN identity).
4. If no match, inserts a new ``devices`` row. The row's MAC/IP may be
   ``NULL`` (legal because ``ha_device_id`` is non-null — the CHECK
   constraint ``devices_identifier_present`` accepts it).

``clear_ha_provenance(session)`` strips HA columns from every devices row
when the connection is deleted. Rows that no longer have a scanner trail
fall through the existing stale-device pipeline on a later scan.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select

from app.models.device import Device
from app.models.ha_entity_snapshot import HAEntitySnapshot
from app.models.home_assistant_connection import HomeAssistantConnection

logger = logging.getLogger(__name__)


_MAC_RE = re.compile(r"^[0-9a-fA-F]{2}([:-][0-9a-fA-F]{2}){5}$")
_IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalise_mac(value: Any) -> str | None:
    """Canonicalise a MAC to lower-case colon form, or return None."""
    if not isinstance(value, str):
        return None
    v = value.strip().lower().replace("-", ":")
    if not _MAC_RE.match(v):
        return None
    return v


def _normalise_ip(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not _IP_RE.match(v):
        return None
    return v


def _first_friendly_name(rows: list[HAEntitySnapshot]) -> str | None:
    """Pick a representative friendly_name for a device group.

    Heuristic: prefer a ``device_tracker`` entity (HA usually names it
    after the device itself), else the entity with the longest
    friendly_name (more specific), else any.
    """
    for row in rows:
        if row.domain == "device_tracker" and row.friendly_name:
            return row.friendly_name
    sortable = [r for r in rows if r.friendly_name]
    if not sortable:
        return None
    return max(sortable, key=lambda r: len(r.friendly_name)).friendly_name


def _derive_connectivity_type(rows: list[HAEntitySnapshot], mac: str | None, ip: str | None) -> str:
    """Classify a device's connectivity from its entity attribute mix.

    Heuristic (documented inline because the HA schema has no canonical
    enum for this):

    * any entity with ``attributes.integration == "thread"`` -> ``thread``
    * any entity with ``zigbee`` referenced in its attributes -> ``zigbee``
    * a resolvable LAN MAC or IP -> ``lan_wifi`` (we can't cheaply tell
      ethernet vs. wifi from HA alone, so collapse to ``lan_wifi`` as the
      default LAN label; the frontend pill says "wifi" / "ethernet" /
      "thread" / "zigbee" / "other")
    * else -> ``other``
    """
    for row in rows:
        attrs = row.attributes or {}
        if attrs.get("integration") == "thread":
            return "thread"
    for row in rows:
        attrs = row.attributes or {}
        # zigbee2mqtt sets ``friendly_name`` but also ``source == "zigbee"``
        # or includes the substring in the integration; check both.
        if str(attrs.get("integration", "")).lower() == "zigbee":
            return "zigbee"
        if "zigbee" in {k.lower() for k in attrs.keys() if isinstance(k, str)}:
            return "zigbee"
    if mac or ip:
        return "lan_wifi"
    return "other"


def _extract_lan_identity(rows: list[HAEntitySnapshot]) -> tuple[str | None, str | None]:
    """Return (mac, ip) pulled from any entity's attributes, or (None, None)."""
    mac: str | None = None
    ip: str | None = None
    for row in rows:
        attrs = row.attributes or {}
        if mac is None:
            mac = _normalise_mac(attrs.get("mac"))
        if ip is None:
            ip = _normalise_ip(attrs.get("ip")) or _normalise_ip(attrs.get("ip_address"))
        if mac and ip:
            break
    return mac, ip


async def _match_existing_device(
    session, ha_device_id: str, mac: str | None, ip: str | None
) -> Device | None:
    """Find an existing ``devices`` row by ha_device_id, then MAC, then IP."""
    # 1) HA device_id (already merged in a prior cycle).
    q = select(Device).where(Device.ha_device_id == ha_device_id).limit(1)
    row = (await session.execute(q)).scalar_one_or_none()
    if row is not None:
        return row

    # 2) LAN MAC (scanner-authoritative for LAN identity).
    if mac is not None:
        q = select(Device).where(Device.mac_address == mac).limit(1)
        row = (await session.execute(q)).scalar_one_or_none()
        if row is not None:
            return row

    # 3) LAN IP — lower-confidence match, only used when MAC lookup missed.
    if ip is not None:
        q = select(Device).where(Device.ip_address == ip).limit(1)
        row = (await session.execute(q)).scalar_one_or_none()
        if row is not None:
            return row

    return None


async def merge_ha_devices(
    session,
    snapshots: list[HAEntitySnapshot],
    conn: HomeAssistantConnection,  # noqa: ARG001 — future use (per-connection provenance)
) -> dict[str, int]:
    """Merge HA-known devices into the unified ``devices`` table.

    Idempotent — safe to run on every poll cycle. Returns a small stats
    dict (matched / created) for the caller's log line.
    """
    now = _utcnow()

    by_device: dict[str, list[HAEntitySnapshot]] = defaultdict(list)
    for row in snapshots:
        if not row.ha_device_id:
            continue
        by_device[row.ha_device_id].append(row)

    matched = 0
    created = 0

    for ha_device_id, rows in by_device.items():
        mac, ip = _extract_lan_identity(rows)
        connectivity = _derive_connectivity_type(rows, mac, ip)
        friendly = _first_friendly_name(rows)

        device = await _match_existing_device(session, ha_device_id, mac, ip)

        if device is not None:
            # Attach HA provenance without overwriting scanner MAC/IP (FR-027).
            device.ha_device_id = ha_device_id
            device.ha_connectivity_type = connectivity
            device.ha_last_seen_at = now
            matched += 1
            continue

        new_device = Device(
            mac_address=mac,
            ip_address=ip,
            hostname=friendly,
            ha_device_id=ha_device_id,
            ha_connectivity_type=connectivity,
            ha_last_seen_at=now,
            first_seen=now,
            last_seen=now,
            is_online=True,
            is_known_device=True,
            monitor_offline=False,  # HA already tracks these.
        )
        session.add(new_device)
        created += 1

    if matched or created:
        logger.info(
            "ha_inventory_merge",
            extra={
                "event": "ha_inventory_merge",
                "matched_count": matched,
                # "created" is a reserved LogRecord attribute — use an
                # unambiguous key so python-json-logger doesn't KeyError.
                "created_count": created,
                "device_count": len(by_device),
            },
        )

    return {"matched": matched, "created": created}


async def clear_ha_provenance(session) -> int:
    """Strip HA provenance columns from every ``devices`` row.

    Used when the HA connection is deleted (FR-029). Scanner-discovered
    rows stay intact — only the ``ha_*`` columns are nulled. Rows that no
    longer have any source of truth fall through the existing
    stale-device pipeline (they are NOT deleted here).

    Returns the count of affected rows for logging.
    """
    q = select(Device).where(Device.ha_device_id.is_not(None))
    rows = (await session.execute(q)).scalars().all()
    for row in rows:
        row.ha_device_id = None
        row.ha_connectivity_type = None
        row.ha_last_seen_at = None
    if rows:
        logger.info(
            "ha_inventory_merge.cleared",
            extra={
                "event": "ha_inventory_merge.cleared",
                "affected": len(rows),
            },
        )
    return len(rows)
