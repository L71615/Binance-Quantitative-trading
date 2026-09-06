"""JSON structured logging with trace_id auto-embedded.

CEO plan F8: every log line is JSON with timestamp / level / logger /
message / trace_id. trace_id comes from `app.trace` so a tick's logs can
be `grep trace=<id>`-ed to reconstruct one decision end-to-end.

Why JSON: the alternative is human-readable formatted lines that a
junior might prefer but cannot be parsed by jq, Loki, Datadog, or any
structured log backend. JSON keeps the door open for production log
shipping later. We accept the readability cost because the operator who
needs to debug at 2am is going to be piping through `jq` anyway.

Setup is idempotent: calling `configure_logging()` twice does not stack
handlers or duplicate log lines. Safe to call from main.py lifespan and
from tests.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, UTC

from app.trace import current_trace_id

# Default level can be overridden via env LOG_LEVEL (INFO / DEBUG / WARNING).
import os

_DEFAULT_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Render each LogRecord as a single-line JSON object.

    Fields:
      ts:        ISO-8601 UTC, second precision.
      level:     "INFO" / "WARNING" / etc.
      logger:    logger name (usually the module path).
      message:   the formatted message.
      trace_id:  from app.trace — see that module for propagation rules.
      exc_info:  present only when the record carries an exception;
                 includes type, message, and the formatted traceback
                 so the operator does not need to walk frames separately.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": current_trace_id(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Any `extra={...}` passed to the log call lands in __dict__ under
        # keys that aren't standard LogRecord attributes. Forward them so
        # domain-specific fields (symbol, order_id, ...) propagate.
        standard = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName",
        }
        for key, val in record.__dict__.items():
            if key not in standard and not key.startswith("_"):
                payload[key] = val
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(*, level: str | None = None) -> None:
    """Install the JSON formatter on the root logger.

    Idempotent: replaces existing handlers rather than appending, so
    calling twice does not double-log. The level argument overrides
    `LOG_LEVEL` for this call only."""
    global _CONFIGURED
    root = logging.getLogger()
    # Tear down any prior handlers — both ours and any default stderr
    # one Python installed implicitly. We re-add a single stderr handler.
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level or _DEFAULT_LEVEL)
    _CONFIGURED = True


def is_configured() -> bool:
    return _CONFIGURED
