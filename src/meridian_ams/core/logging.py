import logging
import sys
import uuid
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import structlog
from structlog.processors import ExceptionRenderer
from structlog.tracebacks import ExceptionDictTransformer
from structlog.types import EventDict, Processor


def _json_default(obj: Any) -> Any:
    """Serialize types the stdlib JSON encoder rejects; repr() as a last resort."""

    if isinstance(obj, uuid.UUID | Path):
        return str(obj)
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value

    return repr(obj)


def configure_logging(
    *,
    log_level: str,
    json_logs: bool,
    environment: str,
) -> None:
    """
    Route structlog, uvicorn and third-party library logs through one
    stdout pipeline.

    json_logs=False -> readable console output (development, test).
    json_logs=True  -> one JSON object per line (production).

    Call once at app creation, before anything logs. `log_level` must be a
    valid stdlib level name (validated in Settings).
    """

    level = logging.getLevelNamesMapping()[log_level.upper()]

    def add_environment(
        logger: Any, method_name: str, event_dict: EventDict
    ) -> EventDict:
        event_dict["environment"] = environment
        return event_dict

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        add_environment,
        structlog.processors.StackInfoRenderer(),
    ]

    renderer_chain: list[Processor]
    if json_logs:
        renderer_chain = [
            # show_locals=False: never dump local variables into logs,
            # they can hold passwords or tokens.
            ExceptionRenderer(ExceptionDictTransformer(show_locals=False)),
            structlog.processors.JSONRenderer(default=_json_default),
        ]
    else:
        renderer_chain = [structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *renderer_chain,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    # RequestLoggingMiddleware already logs every request; skip uvicorn's copy.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Keep SQL statements and pool chatter out of the logs, even at DEBUG.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
