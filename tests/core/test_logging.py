import json
import logging
import uuid
from datetime import UTC, datetime
from enum import Enum

import pytest
import structlog

from meridian_ams.core.logging import configure_logging


class Color(Enum):
    RED = "red"


@pytest.fixture(autouse=True)
def restore_logging_state():
    """configure_logging changes global state, so put it back after each test."""

    root = logging.getLogger()
    old_handlers, old_level = root.handlers[:], root.level

    yield

    root.handlers = old_handlers
    root.setLevel(old_level)
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def _configure_json(level: str = "INFO") -> None:
    configure_logging(log_level=level, json_logs=True, environment="production")


def _read_json_lines(capsys: pytest.CaptureFixture[str]) -> list[dict]:
    out = capsys.readouterr().out

    return [json.loads(line) for line in out.splitlines() if line.strip()]


class TestJsonOutput:
    def test_line_has_standard_fields(self, capsys):
        _configure_json()
        structlog.contextvars.bind_contextvars(request_id="abc-123")

        structlog.get_logger("test_logger").info("something_happened", user_id=5)

        (line,) = _read_json_lines(capsys)

        assert line["event"] == "something_happened"
        assert line["level"] == "info"
        assert line["logger"] == "test_logger"
        assert line["environment"] == "production"
        assert line["request_id"] == "abc-123"
        assert line["user_id"] == 5
        assert "timestamp" in line

    def test_debug_is_dropped_at_info_level(self, capsys):
        _configure_json("INFO")

        structlog.get_logger("test_logger").debug("too_quiet")

        assert capsys.readouterr().out == ""

    def test_exception_is_serialized_without_locals(self, capsys):
        _configure_json()
        logger = structlog.get_logger("test_logger")

        try:
            local_secret = "hunter2"  # noqa: F841
            raise ValueError("boom")

        except ValueError:
            logger.exception("operation_failed")

        out = capsys.readouterr().out
        (line,) = [json.loads(row) for row in out.splitlines() if row.strip()]

        assert "exception" in line
        assert "ValueError" in out
        assert "hunter2" not in out

    def test_uuid_datetime_and_enum_fields_are_serialized(self, capsys):
        _configure_json()
        some_id = uuid.uuid4()
        now = datetime.now(UTC)

        structlog.get_logger("test_logger").info(
            "types", some_id=some_id, at=now, color=Color.RED
        )

        (line,) = _read_json_lines(capsys)

        assert line["some_id"] == str(some_id)
        assert line["at"] == now.isoformat()
        assert line["color"] == "red"


class TestForeignLoggers:
    def test_stdlib_logger_goes_through_same_pipeline(self, capsys):
        _configure_json()

        logging.getLogger("some.library").warning("from_library")

        (line,) = _read_json_lines(capsys)

        assert line["event"] == "from_library"
        assert line["level"] == "warning"
        assert line["logger"] == "some.library"
        assert line["environment"] == "production"


class TestConsoleOutput:
    def test_console_mode_is_not_json(self, capsys):
        configure_logging(log_level="INFO", json_logs=False, environment="development")

        structlog.get_logger("test_logger").info("hello_console")

        out = capsys.readouterr().out

        assert "hello_console" in out
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)
