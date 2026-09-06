"""P0-3 (CEO plan F8): structured JSON logging + trace_id propagation.

Pin the contract:
  - trace_id mints fresh per tick, propagates through nested binds.
  - Log records are single-line JSON with ts/level/logger/message/trace_id.
  - bind_trace context manager yields the bound id and restores on exit.
  - tick() emits tick.start / tick.end lines that carry the trace_id.
"""
import asyncio
import io
import json
import logging
import re

import pytest

from app.db import Base, SessionLocal, engine
from app.logging_config import configure_logging
from app.migrations import run_all_migrations
from app.models.ai_settings import load_or_create
from app.services.ai_trader.service import AITraderService
from app.trace import (
    _NO_TRACE_ID,
    _reset_for_tests,
    bind_trace,
    current_trace_id,
    new_trace_id,
)


def _fresh() -> None:
    """Inline reset called at the top of every test. Cheaper than relying
    on a fixture because contextvars behave subtly under pytest-asyncio's
    per-test event loop scoping; explicit beats implicit."""
    _reset_for_tests()


# ----- trace_id ---------------------------------------------------------------


def test_no_trace_placeholder_is_stable():
    _fresh()
    """Outside any tick, current_trace_id returns a stable per-process
    placeholder so logs never have trace_id=null."""
    assert current_trace_id() == _NO_TRACE_ID
    assert current_trace_id() == _NO_TRACE_ID  # stable across calls


def test_new_trace_id_changes_value():
    _fresh()
    """Each new_trace_id() must produce a fresh hex uuid."""
    a = new_trace_id()
    b = new_trace_id()
    assert a != b
    assert re.fullmatch(r"[0-9a-f]{32}", a)
    assert re.fullmatch(r"[0-9a-f]{32}", b)


def test_bind_trace_yields_and_restores():
    _fresh()
    """bind_trace context manager exposes the bound id and restores the
    previous id (or placeholder) on exit."""
    assert current_trace_id() == _NO_TRACE_ID
    with bind_trace() as tid:
        assert tid == current_trace_id()
        assert tid != _NO_TRACE_ID
    assert current_trace_id() == _NO_TRACE_ID


def test_bind_trace_restores_previous():
    _fresh()
    """Nested bind_trace exits cleanly to the outer id."""
    # Outer bind mints outer_id; nested bind mints inner_id; the inner
    # bind's exit must restore outer_id, then the outer bind's exit must
    # restore the placeholder.
    with bind_trace() as outer_id:
        assert current_trace_id() == outer_id
        with bind_trace() as inner_id:
            assert inner_id != outer_id
            assert current_trace_id() == inner_id
        # Inner block exited — outer is back.
        assert current_trace_id() == outer_id
    # Outer block exited — placeholder is back.
    assert current_trace_id() == _NO_TRACE_ID


def test_bind_trace_can_inherit_id():
    _fresh()
    """Passing an id to bind_trace uses it verbatim instead of minting."""
    given = "deadbeef" * 4
    with bind_trace(given) as tid:
        assert tid == given
        assert current_trace_id() == given


# ----- JSON formatter ---------------------------------------------------------


@pytest.fixture
def captured_logs():
    """Install the JSON formatter on root and capture stderr-equivalent output."""
    _fresh()
    configure_logging(level="DEBUG")
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    from app.logging_config import JsonFormatter
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    # Add the buffer handler alongside the configured stderr one so we can
    # also assert on the root configuration being active.
    root.addHandler(handler)
    yield buf
    root.removeHandler(handler)


def test_log_records_are_valid_json_with_trace_id(captured_logs):
    log = logging.getLogger("test.logger")
    with bind_trace("trace-xyz"):
        log.info("hello %s", "world", extra={"symbol": "BTCUSDT"})
    line = captured_logs.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)  # raises if not JSON
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert payload["trace_id"] == "trace-xyz"
    assert payload["symbol"] == "BTCUSDT"
    assert payload["ts"].endswith("Z")


def test_log_records_use_placeholder_when_no_trace(captured_logs):
    log = logging.getLogger("test.no_trace")
    log.warning("orphan warning")
    line = captured_logs.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["trace_id"].startswith("no-trace-")
    assert payload["level"] == "WARNING"


def test_exception_info_serialized(captured_logs):
    log = logging.getLogger("test.exc")
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("bad thing")
    line = captured_logs.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert "exc_info" in payload
    assert "ValueError" in payload["exc_info"]
    assert "boom" in payload["exc_info"]


def test_configure_logging_is_idempotent():
    """Re-running configure_logging must not stack handlers (which would
    duplicate every log line)."""
    # Reset to a known state first — other tests in this module add buffer
    # handlers via captured_logs. We want the assertion to be independent
    # of test ordering.
    import logging as _lg
    root = _lg.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    configure_logging()
    first = len(root.handlers)
    configure_logging()
    second = len(root.handlers)
    assert first == second, f"handler count drifted: {first} -> {second}"
    assert first == 1, f"expected exactly 1 handler, got {first}"


# ----- tick() integration ----------------------------------------------------


@pytest.fixture
def _clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    run_all_migrations(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.mark.asyncio
async def test_tick_emits_structured_lines_with_trace_id(_clean_db, capsys):
    """Run a real tick() against an empty service and assert the emitted
    log lines are JSON with a trace_id matching the bind inside tick.

    Uses capsys to capture stderr (where the JSON formatter writes) so the
    test doesn't have to fight the root-handler management that
    configure_logging() does."""
    _fresh()
    # Reset root handlers so configure_logging installs its single stderr
    # handler cleanly. Without this, other tests' handlers would carry
    # over and make `configure_logging` look non-idempotent.
    for h in list(logging.getLogger().handlers):
        logging.getLogger().removeHandler(h)
    configure_logging(level="DEBUG")

    with SessionLocal() as s:
        row = load_or_create(s)
        row.status = "running"
        row.symbols = "[\"BTCUSDT\"]"
        s.commit()

    svc = AITraderService(is_paper=False)
    # broker / llm not wired → _tick_symbol returns early, but tick.start
    # and tick.end still emit.
    await svc.tick()

    captured = capsys.readouterr().err
    lines = [json.loads(l) for l in captured.strip().splitlines() if l.strip()]
    starts = [l for l in lines if l.get("message") == "tick.start"]
    ends = [l for l in lines if l.get("message") == "tick.end"]
    assert starts, (
        f"expected a tick.start line, got messages="
        f"{[l.get('message') for l in lines]}"
    )
    assert ends, (
        f"expected a tick.end line, got messages="
        f"{[l.get('message') for l in lines]}"
    )

    # Every tick.start / tick.end line carries a trace_id. The id on tick.end
    # should equal the id on tick.start (same bind_trace scope).
    assert starts[0]["trace_id"] == ends[0]["trace_id"]
    assert starts[0]["trace_id"] != _NO_TRACE_ID
    # tick.start carries the is_paper flag from the service.
    assert starts[0]["is_paper"] is False
