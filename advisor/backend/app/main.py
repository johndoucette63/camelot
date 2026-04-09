import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pythonjsonlogger.json import JsonFormatter

from app.routers import ai_context, devices, events, health, scans

# Structured JSON logging
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter(fmt="%(asctime)s %(levelname)s %(name)s %(message)s"))
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)

logger = logging.getLogger(__name__)

app = FastAPI(title="Network Advisor", version="0.2.0")

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

logger.info("Network Advisor backend started")
