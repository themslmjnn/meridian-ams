import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Literal, TypedDict

import structlog
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)

CHECK_TIMEOUT_SECONDS = 2.0


class CheckResult(TypedDict):
    status: Literal["ok", "error"]
    duration_ms: float


async def _timed_check(
    name: str, check: Callable[[], Awaitable[object]]
) -> CheckResult:
    start = time.perf_counter()
    outcome: Literal["ok", "error"] = "ok"

    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            await check()

    except Exception as exc:
        logger.warning(
            "health_check_failed",
            check=name,
            error=repr(exc),
        )

        outcome = "error"

    return {
        "status": outcome,
        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
    }


async def _ping_database(request: Request) -> None:
    async with request.app.state.engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


@router.get("/live")
async def liveness() -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ok"})


@router.get("/ready")
async def readiness(request: Request) -> JSONResponse:
    (database,) = await asyncio.gather(
        _timed_check("database", lambda: _ping_database(request))
    )

    healthy = database["status"] == "ok"

    return JSONResponse(
        status_code=(
            status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        content={
            "status": "ok" if healthy else "error",
            "checks": {"database": database},
        },
    )
