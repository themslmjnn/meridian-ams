import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import Any, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Select, asc, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings

settings = get_settings()

T = TypeVar("T")

_ENCODING = "utf-8"


class CursorPage[T](BaseModel):
    items: list[T]
    next_cursor: str | None
    prev_cursor: str | None
    limit: int


def _sign(payload: str) -> str:
    return hmac.new(
        settings.CURSOR_SECRET.encode(_ENCODING),
        payload.encode(_ENCODING),
        hashlib.sha256,
    ).hexdigest()


def encode_cursor(created_at: datetime, record_id: int) -> str:
    """Encode (created_at, id) into an opaque, tamper-proof cursor string."""
    payload = json.dumps(
        {"created_at": created_at.isoformat(), "id": record_id},
        separators=(",", ":"),
    )

    signature = _sign(payload)
    token = json.dumps({"p": payload, "s": signature}, separators=(",", ":"))

    return base64.urlsafe_b64encode(token.encode(_ENCODING)).decode(_ENCODING)


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    """
    Decode and verify a cursor string.
    Raises HTTP 422 on any tampering or malformation.
    """
    try:
        token = json.loads(base64.urlsafe_b64decode(cursor.encode(_ENCODING)))
        payload: str = token["p"]
        signature: str = token["s"]

    except Exception:
        _invalid_cursor()

    expected = _sign(payload)
    if not hmac.compare_digest(expected, signature):
        _invalid_cursor()

    try:
        data = json.loads(payload)
        created_at = datetime.fromisoformat(data["created_at"])
        record_id = int(data["id"])

    except Exception:
        _invalid_cursor()

    return created_at, record_id


def _invalid_cursor() -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Invalid or tampered pagination cursor.",
    )


async def paginate(
    session: AsyncSession,
    query: Select,
    *,
    model: Any,
    limit: int = 20,
    next_cursor: str | None = None,
    prev_cursor: str | None = None,
) -> CursorPage:
    """
    Apply cursor-based pagination to a base SELECT query.

    Exactly one of next_cursor / prev_cursor should be provided per request.
    Both None means first page.
    """
    limit = max(1, min(limit, 100))
    fetch = limit + 1

    if next_cursor:
        created_at, record_id = decode_cursor(next_cursor)
        query = (
            query.where(
                text("(created_at, id) < (:cur_created_at, :cur_id)").bindparams(
                    cur_created_at=created_at,
                    cur_id=record_id,
                )
            )
            .order_by(desc(model.created_at), desc(model.id))
            .limit(fetch)
        )

        direction = "forward"

    elif prev_cursor:
        created_at, record_id = decode_cursor(prev_cursor)

        query = (
            query.where(
                text("(created_at, id) > (:cur_created_at, :cur_id)").bindparams(
                    cur_created_at=created_at,
                    cur_id=record_id,
                )
            )
            .order_by(asc(model.created_at), asc(model.id))
            .limit(fetch)
        )

        direction = "backward"

    else:
        query = query.order_by(desc(model.created_at), desc(model.id)).limit(fetch)

        direction = "forward"

    result = await session.execute(query)
    rows = list(result.scalars().all())

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    if direction == "backward":
        rows.reverse()

    if not rows:
        return CursorPage(items=[], next_cursor=None, prev_cursor=None, limit=limit)

    first = rows[0]
    last = rows[-1]

    built_next = (
        encode_cursor(last.created_at, last.id)
        if has_more or direction == "backward"
        else None
    )
    built_prev = (
        encode_cursor(first.created_at, first.id)
        if next_cursor or (direction == "backward" and has_more)
        else None
    )

    return CursorPage(
        items=rows, next_cursor=built_next, prev_cursor=built_prev, limit=limit
    )
