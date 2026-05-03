import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import docker
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pythonjsonlogger.json import JsonFormatter

from app.routers import (
    ai_context,
    alerts,
    chat,
    containers,
    dashboard,
    devices,
    events,
    health,
    home_assistant,
    infra,
    notes,
    recommendations,
    scans,
    services,
    settings as settings_router,
    vpn,
)
from app.services import rule_engine
from app.services.ha_poller import run_ha_poller
from app.services.health_checker import run_health_checker

# Structured JSON logging
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter(fmt="%(asctime)s %(levelname)s %(name)s %(message)s"))
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        app.state.docker = docker.from_env()
    except docker.errors.DockerException:
        app.state.docker = None
        logger.warning("Docker socket not available — container discovery disabled")

    app.state.container_state = {
        "running": [],
        "stopped": [],
        "refreshed_at": None,
        "socket_error": True,
    }
    app.state.hosts_unreachable = set()

    health_task = asyncio.create_task(run_health_checker(app))
    rule_engine_task = asyncio.create_task(rule_engine.run(app))
    ha_poller_task = asyncio.create_task(run_ha_poller())
    logger.info("Network Advisor backend started")

    yield

    # Shutdown
    health_task.cancel()
    rule_engine_task.cancel()
    ha_poller_task.cancel()
    for task in (health_task, rule_engine_task, ha_poller_task):
        try:
            await task
        except asyncio.CancelledError:
            pass

    if app.state.docker:
        app.state.docker.close()
    logger.info("Network Advisor backend stopped")


app = FastAPI(title="Network Advisor", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://advisor.holygrail"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ai_context.router, prefix="/ai-context", tags=["ai-context"])
app.include_router(devices.router, prefix="/devices", tags=["devices"])
app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(scans.router, prefix="/scans", tags=["scans"])
app.include_router(containers.router, prefix="/containers", tags=["containers"])
app.include_router(services.router, prefix="/services", tags=["services"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(notes.router, prefix="/notes", tags=["notes"])
app.include_router(recommendations.router)
app.include_router(alerts.router)
app.include_router(settings_router.router)
app.include_router(vpn.router)
app.include_router(home_assistant.router)
app.include_router(infra.router)
