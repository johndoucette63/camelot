"""GET /dashboard/summary — overall system health summary."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.health_check_result import HealthCheckResult
from app.models.home_assistant_connection import HomeAssistantConnection
from app.models.service_definition import ServiceDefinition

router = APIRouter()


async def get_db():
    async with async_session() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


def _iso(dt) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _ha_status(conn: HomeAssistantConnection | None) -> str:
    """Derive the HA integration status for the dashboard summary.

    Mirrors the mapping used by ``GET /settings/home-assistant`` and
    ``GET /ha/entities`` so the UI can read a single status code across
    surfaces (FR-025).
    """
    if conn is None or conn.base_url is None:
        return "not_configured"
    if conn.last_error:
        last = conn.last_error
        if last in ("auth_failure", "unreachable", "unexpected_payload"):
            return last
        return "unreachable"
    return "ok"


@router.get("/summary")
async def dashboard_summary(request: Request, db: DbDep):
    """Compute healthy/degraded/down/unchecked counts with per-host breakdown."""
    svcs = (
        await db.execute(
            select(ServiceDefinition).where(ServiceDefinition.enabled.is_(True))
        )
    ).scalars().all()

    total = len(svcs)
    healthy = 0
    degraded = 0
    down = 0
    unchecked = 0
    host_data: dict[str, dict] = {}

    for svc in svcs:
        latest = (
            await db.execute(
                select(HealthCheckResult)
                .where(HealthCheckResult.service_id == svc.id)
                .order_by(HealthCheckResult.checked_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        status = latest.status if latest else None

        if status == "green":
            healthy += 1
        elif status == "yellow":
            degraded += 1
        elif status == "red":
            down += 1
        else:
            unchecked += 1

        host = host_data.setdefault(
            svc.host_label, {"label": svc.host_label, "total": 0, "healthy": 0, "degraded": 0, "down": 0}
        )
        host["total"] += 1
        if status == "green":
            host["healthy"] += 1
        elif status == "yellow":
            host["degraded"] += 1
        elif status == "red":
            host["down"] += 1

    hosts_unreachable = sorted(request.app.state.hosts_unreachable)

    # Home Assistant integration block (feature 016, T029b / FR-025).
    # The dashboard reads the singleton row and exposes its health
    # alongside service counts so the nav status pill sees one unified
    # summary shape.
    ha_conn = await db.get(HomeAssistantConnection, 1)
    ha_block = {
        "configured": ha_conn is not None and ha_conn.base_url is not None,
        "status": _ha_status(ha_conn),
        "last_success_at": _iso(ha_conn.last_success_at) if ha_conn else None,
        "last_error": ha_conn.last_error if ha_conn else None,
    }

    return {
        "total": total,
        "healthy": healthy,
        "degraded": degraded,
        "down": down,
        "unchecked": unchecked,
        "hosts": list(host_data.values()),
        "hosts_unreachable": hosts_unreachable,
        "integrations": {
            "home_assistant": ha_block,
        },
    }
