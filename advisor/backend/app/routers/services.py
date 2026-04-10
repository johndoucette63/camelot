"""GET /services — service definitions with latest health status."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.health_check_result import HealthCheckResult
from app.models.service_definition import ServiceDefinition

router = APIRouter()


async def get_db():
    async with async_session() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("")
async def list_services(db: DbDep):
    """Return all enabled services with their latest health check result."""
    svcs = (
        await db.execute(
            select(ServiceDefinition).where(ServiceDefinition.enabled.is_(True))
        )
    ).scalars().all()

    results = []
    for svc in svcs:
        # Get the most recent health check result for this service
        latest_row = (
            await db.execute(
                select(HealthCheckResult)
                .where(HealthCheckResult.service_id == svc.id)
                .order_by(HealthCheckResult.checked_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        latest = None
        if latest_row:
            latest = {
                "status": latest_row.status,
                "checked_at": latest_row.checked_at.isoformat() + "Z",
                "response_time_ms": latest_row.response_time_ms,
                "error": latest_row.error,
            }

        results.append({
            "id": svc.id,
            "name": svc.name,
            "host_label": svc.host_label,
            "host": svc.host,
            "port": svc.port,
            "check_type": svc.check_type,
            "enabled": svc.enabled,
            "latest": latest,
        })

    return results


@router.get("/{service_id}/history")
async def service_history(
    service_id: int,
    db: DbDep,
    hours: int = Query(default=24, ge=1, le=168),
):
    """Return health check history for a single service."""
    svc = (
        await db.execute(
            select(ServiceDefinition).where(ServiceDefinition.id == service_id)
        )
    ).scalar_one_or_none()

    if not svc or not svc.enabled:
        raise HTTPException(status_code=404, detail="Service not found")

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    rows = (
        await db.execute(
            select(HealthCheckResult)
            .where(
                HealthCheckResult.service_id == service_id,
                HealthCheckResult.checked_at >= cutoff,
            )
            .order_by(HealthCheckResult.checked_at.desc())
        )
    ).scalars().all()

    return {
        "service": {
            "id": svc.id,
            "name": svc.name,
            "host_label": svc.host_label,
            "host": svc.host,
            "port": svc.port,
            "check_type": svc.check_type,
        },
        "history": [
            {
                "checked_at": r.checked_at.isoformat() + "Z",
                "status": r.status,
                "response_time_ms": r.response_time_ms,
                "error": r.error,
            }
            for r in rows
        ],
    }
