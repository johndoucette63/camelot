"""AI context endpoint.

Provides a single JSON bundle of all device annotations and recent events
(last 24 hours) for use by the AI advisor chat feature. Called by the AI
chat implementation to populate its system prompt context.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.device import Device
from app.models.event import Event

router = APIRouter()


async def get_db():
    async with async_session() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


class AiContextDevice(BaseModel):
    # mac / ip nullable for HA-only devices (feature 016).
    mac: str | None
    ip: str | None
    hostname: str | None
    role: str
    description: str | None
    tags: list[str]
    is_online: bool
    os_family: str | None = None
    classification_source: str | None = None


class AiContextEvent(BaseModel):
    event_type: str
    timestamp: str
    device_mac: str | None
    device_hostname: str | None
    details: dict | None


class AiContextResponse(BaseModel):
    devices: list[AiContextDevice]
    events: list[AiContextEvent]


@router.get("", response_model=AiContextResponse)
async def get_ai_context(db: DbDep) -> AiContextResponse:
    """Return all device annotations and last-24h events for AI context."""
    # All devices with annotations
    device_result = await db.execute(
        select(Device).options(selectinload(Device.annotation))
    )
    devices = device_result.scalars().all()

    device_out = []
    for d in devices:
        device_out.append(
            AiContextDevice(
                mac=d.mac_address,
                ip=d.ip_address,
                hostname=d.hostname,
                role=d.annotation.role if d.annotation else "unknown",
                description=d.annotation.description if d.annotation else None,
                tags=d.annotation.tags if d.annotation else [],
                is_online=d.is_online,
                os_family=d.os_family,
                classification_source=d.annotation.classification_source if d.annotation else None,
            )
        )

    # Events from last 24 hours
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    event_result = await db.execute(
        select(Event)
        .options(selectinload(Event.device))
        .where(Event.timestamp >= cutoff)
        .order_by(Event.timestamp.desc())
    )
    recent_events = event_result.scalars().all()

    events_out = []
    for ev in recent_events:
        events_out.append(
            AiContextEvent(
                event_type=ev.event_type,
                timestamp=ev.timestamp.isoformat() + "Z",
                device_mac=ev.device.mac_address if ev.device else None,
                device_hostname=ev.device.hostname if ev.device else None,
                details=ev.details,
            )
        )

    return AiContextResponse(devices=device_out, events=events_out)
