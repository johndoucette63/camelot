import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import engine

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check() -> JSONResponse:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "database": "connected"},
        )
    except Exception as e:
        logger.warning("Health check failed: database unreachable", extra={"error": str(e)})
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "disconnected"},
        )
