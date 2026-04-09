from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.event import Event

router = APIRouter()


async def get_db():
    async with async_session() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


class EventDeviceOut(BaseModel):
    mac_address: str
    ip_address: str
    hostname: str | None
    vendor: str | None


class EventOut(BaseModel):
    id: int
    event_type: str
    timestamp: str
    device: EventDeviceOut | None
    details: dict | None


class EventsResponse(BaseModel):
    total: int
    events: list[EventOut]


@router.get("", response_model=EventsResponse)
async def list_events(
    db: DbDep,
    type: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
) -> EventsResponse:
    stmt = (
        select(Event)
        .options(selectinload(Event.device))
        .order_by(desc(Event.timestamp))
    )

    if type is not None:
        stmt = stmt.where(Event.event_type == type)

    if since is not None:
        since_naive = since.replace(tzinfo=None) if since.tzinfo else since
        stmt = stmt.where(Event.timestamp >= since_naive)

    # Count total (before pagination)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Apply pagination
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    events = result.scalars().all()

    event_outs = []
    for ev in events:
        device_out = None
        if ev.device:
            device_out = EventDeviceOut(
                mac_address=ev.device.mac_address,
                ip_address=ev.device.ip_address,
                hostname=ev.device.hostname,
                vendor=ev.device.vendor,
            )
        event_outs.append(
            EventOut(
                id=ev.id,
                event_type=ev.event_type,
                timestamp=ev.timestamp.isoformat() + "Z",
                device=device_out,
                details=ev.details,
            )
        )

    return EventsResponse(total=total, events=event_outs)
