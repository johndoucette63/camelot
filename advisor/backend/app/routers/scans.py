from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.scan import Scan

router = APIRouter()


async def get_db():
    async with async_session() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


class ScanOut(BaseModel):
    id: int
    started_at: str
    completed_at: str | None
    status: str
    devices_found: int | None
    new_devices: int | None
    error_detail: str | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, scan: Scan) -> "ScanOut":
        return cls(
            id=scan.id,
            started_at=scan.started_at.isoformat() + "Z",
            completed_at=(scan.completed_at.isoformat() + "Z") if scan.completed_at else None,
            status=scan.status,
            devices_found=scan.devices_found,
            new_devices=scan.new_devices,
            error_detail=scan.error_detail,
        )


@router.get("", response_model=list[ScanOut])
async def list_scans(db: DbDep, limit: int = 20) -> list[ScanOut]:
    limit = min(limit, 100)
    result = await db.execute(
        select(Scan).order_by(desc(Scan.started_at)).limit(limit)
    )
    scans = result.scalars().all()
    return [ScanOut.from_orm(s) for s in scans]


@router.post("/trigger", status_code=202)
async def trigger_scan(db: DbDep) -> dict:
    # Check if a scan is already running or pending
    result = await db.execute(
        select(Scan).where(Scan.status.in_(["running", "pending"])).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Scan already running")

    # Insert a pending scan row; scanner loop picks it up
    pending = Scan(status="pending")
    db.add(pending)
    await db.commit()
    return {"message": "Scan triggered"}
