import asyncio
import time
from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.database.connection import engine

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


async def _check_database() -> dict[str, Any]:
    """
    Verify PostgreSQL is reachable by executing SELECT 1.

    Uses engine.connect() directly rather than a full ORM session to avoid
    unnecessary overhead in a health endpoint.
    """
    start = time.perf_counter()

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        return {"status": "ok", "duration_ms": duration_ms}

    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.warning("health_db_check_failed", error=str(exc))

        return {"status": "error", "duration_ms": duration_ms, "error": str(exc)}


async def _check_redis(request: Request) -> dict[str, Any]:
    """Verify Redis is reachable by sending a PING command."""
    start = time.perf_counter()

    try:
        await request.app.state.redis.ping()

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        return {"status": "ok", "duration_ms": duration_ms}

    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.warning("health_redis_check_failed", error=str(exc))

        return {"status": "error", "duration_ms": duration_ms, "error": str(exc)}


@router.get("/live")
async def liveness() -> JSONResponse:
    """
    Liveness probe — returns 200 if the process is running.

    No DB or Redis checks. Used by Railway and Docker HEALTHCHECK to determine
    whether to restart the container.
    """
    return JSONResponse(status_code=200, content={"status": "ok"})


@router.get("/ready")
async def readiness(request: Request) -> JSONResponse:
    """
    Readiness probe — checks PostgreSQL and Redis in parallel.

    Returns 200 only when both dependencies are healthy.
    Returns 503 if either check fails.

    Both checks always run regardless of individual failures
    (asyncio.gather with return_exceptions=True).
    """
    db_result, redis_result = await asyncio.gather(
        _check_database(),
        _check_redis(request),
        return_exceptions=True,
    )

    if isinstance(db_result, BaseException):
        db_result = {"status": "error", "error": str(db_result)}
    if isinstance(redis_result, BaseException):
        redis_result = {"status": "error", "error": str(redis_result)}

    all_healthy = (
        db_result.get("status") == "ok"  # type: ignore[union-attr]
        and redis_result.get("status") == "ok"  # type: ignore[union-attr]
    )

    status_code = 200 if all_healthy else 503
    overall_status = "ok" if all_healthy else "error"

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "checks": {
                "database": db_result,
                "redis": redis_result,
            },
        },
    )
