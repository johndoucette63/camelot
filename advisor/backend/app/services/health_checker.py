"""Background health checker — polls Docker containers and probes services."""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from docker.errors import DockerException
from sqlalchemy import delete, select

from app.database import async_session
from app.models.health_check_result import HealthCheckResult
from app.models.service_definition import ServiceDefinition

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60
PURGE_AFTER_DAYS = 7
HTTP_TIMEOUT_SECONDS = 10
TCP_TIMEOUT_SECONDS = 5


# ── Container discovery ──────────────────────────────────────────────────


async def fetch_containers(app) -> None:
    """Fetch Docker containers and update app.state.container_state."""
    try:
        containers = await asyncio.to_thread(
            app.state.docker.containers.list, all=True
        )

        running = []
        stopped = []
        for c in containers:
            info = {
                "id": c.short_id,
                "name": c.name,
                "image": ",".join(c.image.tags) if c.image.tags else c.image.short_id,
                "status": c.status,
                "ports": c.ports or {},
                "uptime": c.attrs.get("State", {}).get("StartedAt", ""),
                "created": c.attrs.get("Created", ""),
            }
            if c.status == "running":
                running.append(info)
            else:
                stopped.append(info)

        app.state.container_state = {
            "running": running,
            "stopped": stopped,
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "socket_error": False,
        }
    except DockerException as exc:
        logger.warning("Docker socket unavailable", extra={"error": str(exc)})
        # Preserve last known containers; mark stale
        app.state.container_state["socket_error"] = True


# ── Health checks ────────────────────────────────────────────────────────


async def check_http(
    host: str, port: int, check_url: str | None, degraded_threshold_ms: int | None
) -> tuple[str, int | None, str | None]:
    """Probe an HTTP endpoint. Returns (status, response_time_ms, error)."""
    url = f"http://{host}:{port}{check_url or '/'}"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            t0 = time.monotonic()
            resp = await client.get(url)
            elapsed_ms = int((time.monotonic() - t0) * 1000)

        if resp.status_code < 200 or resp.status_code >= 400:
            return ("red", elapsed_ms, f"HTTP {resp.status_code}")

        if degraded_threshold_ms and elapsed_ms > degraded_threshold_ms:
            return ("yellow", elapsed_ms, None)

        return ("green", elapsed_ms, None)
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        return ("red", None, str(exc))


async def check_tcp(host: str, port: int) -> tuple[str, int | None, str | None]:
    """Probe a TCP port. Returns (status, response_time_ms, error). Binary: green or red."""
    try:
        t0 = time.monotonic()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=TCP_TIMEOUT_SECONDS
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        writer.close()
        await writer.wait_closed()
        return ("green", elapsed_ms, None)
    except (OSError, asyncio.TimeoutError) as exc:
        return ("red", None, str(exc))


# ── Purge ────────────────────────────────────────────────────────────────


async def purge_old_results(db) -> int:
    """Delete health check results older than PURGE_AFTER_DAYS. Returns count deleted."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=PURGE_AFTER_DAYS)
    result = await db.execute(
        delete(HealthCheckResult).where(HealthCheckResult.checked_at < cutoff)
    )
    return result.rowcount


# ── Host unreachability detection ────────────────────────────────────────

CONNECTION_ERRORS = ("Connection refused", "timed out", "TimeoutError", "No route to host")


def _is_connection_error(error: str | None) -> bool:
    if not error:
        return False
    return any(phrase in error for phrase in CONNECTION_ERRORS)


def detect_unreachable_hosts(
    results_by_host: dict[str, list[tuple[str, str | None]]],
) -> set[str]:
    """Given {host_label: [(status, error), ...]}, return set of unreachable host labels."""
    unreachable = set()
    for host_label, checks in results_by_host.items():
        if not checks:
            continue
        if all(s == "red" and _is_connection_error(e) for s, e in checks):
            unreachable.add(host_label)
    return unreachable


# ── Main loop ────────────────────────────────────────────────────────────


async def run_health_checker(app) -> None:
    """Long-running background task — called once from lifespan."""
    # Brief initial delay to let the app finish startup
    await asyncio.sleep(2)

    while True:
        cycle_start = time.monotonic()
        checked = 0
        results_by_host: dict[str, list[tuple[str, str | None]]] = {}

        try:
            # 1) Refresh Docker containers
            await fetch_containers(app)

            # 2) Run health checks
            async with async_session() as db:
                svcs = (
                    await db.execute(
                        select(ServiceDefinition).where(ServiceDefinition.enabled.is_(True))
                    )
                ).scalars().all()

                for svc in svcs:
                    if svc.check_type == "http":
                        status, ms, err = await check_http(
                            svc.host, svc.port, svc.check_url, svc.degraded_threshold_ms
                        )
                    elif svc.check_type == "tcp":
                        status, ms, err = await check_tcp(svc.host, svc.port)
                    else:
                        status, ms, err = ("red", None, f"Unknown check_type: {svc.check_type}")

                    db.add(HealthCheckResult(
                        service_id=svc.id,
                        checked_at=datetime.now(timezone.utc).replace(tzinfo=None),
                        status=status,
                        response_time_ms=ms,
                        error=err,
                    ))

                    results_by_host.setdefault(svc.host_label, []).append((status, err))
                    checked += 1

                    logger.info(
                        "health_check",
                        extra={
                            "event": "health_check",
                            "service": svc.name,
                            "host": svc.host_label,
                            "status": status,
                            "response_time_ms": ms,
                            "error": err,
                        },
                    )

                # 3) Purge old results
                purged = await purge_old_results(db)
                await db.commit()

            # 4) Update host unreachability state
            app.state.hosts_unreachable = detect_unreachable_hosts(results_by_host)

            duration_ms = int((time.monotonic() - cycle_start) * 1000)
            logger.info(
                "health_check_cycle_complete",
                extra={
                    "event": "health_check_cycle_complete",
                    "checked": checked,
                    "purged": purged,
                    "duration_ms": duration_ms,
                },
            )
        except asyncio.CancelledError:
            logger.info("Health checker shutting down")
            raise
        except Exception:
            logger.exception("Health checker cycle failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
