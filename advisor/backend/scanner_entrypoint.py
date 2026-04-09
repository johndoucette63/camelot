"""Scanner sidecar entrypoint.

Runs on the host network (network_mode: host) so nmap can perform ARP-based
MAC address discovery on the LAN. Connects to PostgreSQL via 127.0.0.1:5432
(the exposed port from the advisor postgres container).
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Configure structured JSON logging before any other imports
import json

class JsonLineHandler(logging.StreamHandler):
    _formatter = logging.Formatter()

    def emit(self, record):
        msg = {
            "time": self._formatter.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra"):
            msg.update(record.extra)
        # Merge any extra fields set via extra= kwarg
        for key in vars(record):
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                msg[key] = getattr(record, key)
        print(json.dumps(msg), flush=True)


handler = JsonLineHandler(sys.stdout)
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)

logger = logging.getLogger("scanner")

# Import after logging is configured
from app.models.event import Event  # noqa: E402
from app.models.scan import Scan  # noqa: E402
from app.services.scanner import run_scan  # noqa: E402

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://john:changeme@127.0.0.1:5432/advisor",
)
SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL_SECONDS", "900"))
SCAN_TARGET = os.environ.get("SCAN_TARGET", "192.168.10.0/24")
RETENTION_DAYS = 30


async def purge_old_events(db: AsyncSession) -> None:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=RETENTION_DAYS)
    await db.execute(delete(Event).where(Event.timestamp < cutoff))
    await db.commit()


async def check_pending_scan(db: AsyncSession) -> Scan | None:
    """Return a pending scan row if one exists (triggered via API)."""
    result = await db.execute(
        select(Scan).where(Scan.status == "pending").limit(1)
    )
    return result.scalar_one_or_none()


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    logger.info("Scanner started", extra={"target": SCAN_TARGET, "interval": SCAN_INTERVAL})

    while True:
        try:
            async with session_factory() as db:
                # Purge stale events
                await purge_old_events(db)

                # Handle pending (API-triggered) scan: delete it so run_scan creates its own
                pending = await check_pending_scan(db)
                if pending:
                    pending.status = "superseded"
                    await db.commit()
                    logger.info("Processing API-triggered scan")

                logger.info("Starting scan", extra={"target": SCAN_TARGET})
                scan = await run_scan(db, target=SCAN_TARGET)
                logger.info(
                    "Scan finished",
                    extra={
                        "status": scan.status,
                        "devices_found": scan.devices_found,
                        "new_devices": scan.new_devices,
                    },
                )
        except Exception as exc:
            logger.error("Scanner loop error", extra={"error": str(exc)})

        await asyncio.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Scanner stopped")
