import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pythonjsonlogger.json import JsonFormatter

from app.routers import health

# Structured JSON logging
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter(fmt="%(asctime)s %(levelname)s %(name)s %(message)s"))
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)

logger = logging.getLogger(__name__)

app = FastAPI(title="Network Advisor", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)

logger.info("Network Advisor backend started")
