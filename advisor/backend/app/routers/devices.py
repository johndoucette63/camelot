from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.annotation import Annotation
from app.models.device import Device
from app.services.scanner import VALID_ROLES

router = APIRouter()


async def get_db():
    async with async_session() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]

SORT_FIELDS = {
    "ip": Device.ip_address,
    "hostname": Device.hostname,
    "mac": Device.mac_address,
    "vendor": Device.vendor,
    "last_seen": Device.last_seen,
}


class AnnotationOut(BaseModel):
    role: str
    description: str | None
    tags: list[str]
    classification_source: str | None = None
    classification_confidence: str | None = None


class DeviceOut(BaseModel):
    id: int
    mac_address: str
    ip_address: str
    hostname: str | None
    vendor: str | None
    first_seen: str
    last_seen: str
    is_online: bool
    is_known_device: bool
    monitor_offline: bool
    os_family: str | None = None
    os_detail: str | None = None
    mdns_name: str | None = None
    netbios_name: str | None = None
    ssdp_friendly_name: str | None = None
    ssdp_model: str | None = None
    last_enriched_at: str | None = None
    annotation: AnnotationOut | None


def _device_to_out(device: Device) -> DeviceOut:
    ann = None
    if device.annotation:
        ann = AnnotationOut(
            role=device.annotation.role,
            description=device.annotation.description,
            tags=device.annotation.tags or [],
            classification_source=device.annotation.classification_source,
            classification_confidence=device.annotation.classification_confidence,
        )
    return DeviceOut(
        id=device.id,
        mac_address=device.mac_address,
        ip_address=device.ip_address,
        hostname=device.hostname,
        vendor=device.vendor,
        first_seen=device.first_seen.isoformat() + "Z",
        last_seen=device.last_seen.isoformat() + "Z",
        is_online=device.is_online,
        is_known_device=device.is_known_device,
        monitor_offline=device.monitor_offline,
        os_family=device.os_family,
        os_detail=device.os_detail,
        mdns_name=device.mdns_name,
        netbios_name=device.netbios_name,
        ssdp_friendly_name=device.ssdp_friendly_name,
        ssdp_model=device.ssdp_model,
        last_enriched_at=device.last_enriched_at.isoformat() + "Z" if device.last_enriched_at else None,
        annotation=ann,
    )


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    db: DbDep,
    online: bool | None = None,
    sort: str = "ip",
    order: Literal["asc", "desc"] = "asc",
    q: str | None = None,
) -> list[DeviceOut]:
    sort_col = SORT_FIELDS.get(sort, Device.ip_address)
    if order == "desc":
        sort_col = sort_col.desc()

    stmt = select(Device).options(selectinload(Device.annotation)).order_by(sort_col)

    if online is not None:
        stmt = stmt.where(Device.is_online == online)

    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Device.hostname.ilike(pattern),
                Device.ip_address.ilike(pattern),
            )
        )

    result = await db.execute(stmt)
    devices = result.scalars().all()
    return [_device_to_out(d) for d in devices]


@router.get("/{mac_address}", response_model=DeviceOut)
async def get_device(mac_address: str, db: DbDep) -> DeviceOut:
    result = await db.execute(
        select(Device)
        .options(selectinload(Device.annotation))
        .where(Device.mac_address == mac_address)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return _device_to_out(device)


class AnnotationIn(BaseModel):
    role: str | None = None
    description: str | None = None
    tags: list[str] | None = None


@router.patch("/{mac_address}/annotation", response_model=DeviceOut)
async def update_annotation(mac_address: str, body: AnnotationIn, db: DbDep) -> DeviceOut:
    result = await db.execute(
        select(Device)
        .options(selectinload(Device.annotation))
        .where(Device.mac_address == mac_address)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if body.role is not None and body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{body.role}'. Valid roles: {sorted(VALID_ROLES)}",
        )

    if device.annotation is None:
        annotation = Annotation(
            device_id=device.id,
            role=body.role or "unknown",
            description=body.description,
            tags=body.tags or [],
            classification_source="user" if body.role else None,
            classification_confidence=None,
        )
        db.add(annotation)
        device.annotation = annotation
    else:
        if body.role is not None:
            device.annotation.role = body.role
            device.annotation.classification_source = "user"
            device.annotation.classification_confidence = None
        if body.description is not None:
            device.annotation.description = body.description
        if body.tags is not None:
            device.annotation.tags = body.tags

    await db.commit()
    await db.refresh(device)
    return _device_to_out(device)


class MonitorOfflineIn(BaseModel):
    monitor_offline: bool


@router.patch("/{mac_address}/monitor-offline", response_model=DeviceOut)
async def toggle_monitor_offline(
    mac_address: str, body: MonitorOfflineIn, db: DbDep
) -> DeviceOut:
    result = await db.execute(
        select(Device)
        .options(selectinload(Device.annotation))
        .where(Device.mac_address == mac_address)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.monitor_offline = body.monitor_offline
    await db.commit()
    await db.refresh(device)
    return _device_to_out(device)


@router.post("/{mac_address}/re-enrich", status_code=202)
async def re_enrich_device(mac_address: str, db: DbDep) -> dict:
    result = await db.execute(
        select(Device).where(Device.mac_address == mac_address)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.last_enriched_at = None
    await db.commit()
    return {"message": "Device queued for re-enrichment", "mac_address": mac_address}
