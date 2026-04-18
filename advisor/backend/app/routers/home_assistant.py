"""Home Assistant read-only endpoints (feature 016, US-1).

Exposes the cached entity snapshot for the dashboard tab. Contract
reference: ``specs/016-ha-integration/contracts/home-assistant-api.md`` §2.

The Thread-view endpoint (§3) belongs to US-2 and is added by a separate
agent in Wave 2; this file intentionally stops at ``/ha/entities``.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.ha_entity_snapshot import HAEntitySnapshot
from app.models.home_assistant_connection import HomeAssistantConnection
from app.models.thread_border_router import ThreadBorderRouter
from app.models.thread_device import ThreadDevice
from app.schemas.home_assistant import (
    HAConnectionStatus,
    HAEntitiesResponse,
    HAEntityOut,
    ThreadBorderRouterOut,
    ThreadDeviceOut,
    ThreadTopologyResponse,
)

router = APIRouter(prefix="/ha", tags=["home-assistant"])


async def get_db():
    async with async_session() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


def _connection_status(conn: HomeAssistantConnection | None) -> HAConnectionStatus:
    """Derive a ``HAConnectionStatus`` from the singleton row."""
    if conn is None or conn.base_url is None:
        return "not_configured"
    if conn.last_error:
        last = conn.last_error
        if last in ("auth_failure", "unreachable", "unexpected_payload"):
            return last  # type: ignore[return-value]
        # Unknown error class in the DB -> treat as unreachable for the UI.
        return "unreachable"
    return "ok"


@router.get("/entities", response_model=HAEntitiesResponse)
async def list_entities(
    db: DbDep,
    domain: list[str] | None = Query(default=None),
    search: str | None = Query(default=None),
    stale_only: bool = Query(default=False),
) -> HAEntitiesResponse:
    """Return the latest HA entity snapshot with optional filters."""
    conn = await db.get(HomeAssistantConnection, 1)
    status = _connection_status(conn)

    # Polled-at is the most recent polled_at across all snapshot rows. Null
    # when the table is empty (i.e. the poller has never succeeded yet).
    polled_at = (
        await db.execute(select(func.max(HAEntitySnapshot.polled_at)))
    ).scalar_one_or_none()

    # Staleness flag: true when the connection is NOT ok but we still have
    # a prior snapshot to show (contract §2, FR-008).
    stale = status != "ok" and polled_at is not None

    q = select(HAEntitySnapshot).order_by(HAEntitySnapshot.last_changed.desc())
    if domain:
        q = q.where(HAEntitySnapshot.domain.in_(domain))
    if search:
        like = f"%{search}%"
        q = q.where(
            or_(
                HAEntitySnapshot.friendly_name.ilike(like),
                HAEntitySnapshot.entity_id.ilike(like),
            )
        )
    rows = (await db.execute(q)).scalars().all()

    if stale_only:
        # Keep only rows older than 1 h per contract §2.
        from datetime import datetime, timedelta, timezone

        one_hour_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        rows = [
            r
            for r in rows
            if (r.last_changed.replace(tzinfo=None) if r.last_changed.tzinfo else r.last_changed)
            < one_hour_ago
        ]

    entities = [
        HAEntityOut(
            entity_id=r.entity_id,
            ha_device_id=r.ha_device_id,
            domain=r.domain,
            friendly_name=r.friendly_name,
            state=r.state,
            last_changed=r.last_changed,
            attributes=r.attributes or {},
        )
        for r in rows
    ]

    return HAEntitiesResponse(
        connection_status=status,
        polled_at=polled_at,
        stale=stale,
        entities=entities,
    )


@router.get("/thread", response_model=ThreadTopologyResponse)
async def get_thread_topology(db: DbDep) -> ThreadTopologyResponse:
    """Return the derived Thread topology (contract §3, FR-010–FR-013)."""
    conn = await db.get(HomeAssistantConnection, 1)
    status = _connection_status(conn)

    router_rows = (
        (await db.execute(select(ThreadBorderRouter))).scalars().all()
    )
    device_rows = (await db.execute(select(ThreadDevice))).scalars().all()

    polled_at = None
    if router_rows:
        polled_at = max(r.last_refreshed_at for r in router_rows)

    orphaned_count = sum(
        1 for d in device_rows if d.parent_border_router_id is None
    )

    empty_reason = None
    if not router_rows and not device_rows and status == "ok":
        empty_reason = "no_thread_integration_data"

    border_routers = [
        ThreadBorderRouterOut(
            ha_device_id=r.ha_device_id,
            friendly_name=r.friendly_name,
            model=r.model,
            online=r.online,
            attached_device_count=r.attached_device_count,
        )
        for r in router_rows
    ]
    devices = [
        ThreadDeviceOut(
            ha_device_id=d.ha_device_id,
            friendly_name=d.friendly_name,
            parent_border_router_id=d.parent_border_router_id,
            online=d.online,
            last_seen_parent_id=d.last_seen_parent_id,
        )
        for d in device_rows
    ]

    return ThreadTopologyResponse(
        connection_status=status,
        polled_at=polled_at,
        border_routers=border_routers,
        devices=devices,
        orphaned_device_count=orphaned_count,
        empty_reason=empty_reason,
    )
