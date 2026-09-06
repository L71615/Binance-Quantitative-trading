"""Per-tick trace id propagated via contextvar.

CEO plan F8: every tick / order / LLM call carries a trace_id so a bug
reported weeks later can be reconstructed by grepping logs.

contextvars were chosen over threading.local because asyncio tasks each
get their own copy of the context — a tick running in `asyncio.create_task`
automatically sees the trace_id set in the parent task, and a child
spawned inside the tick inherits it too. threading.local would NOT
propagate across awaits and would lose the id on every `await`.

Idempotency: `current_trace_id()` returns a per-process stable id
("no-trace-<uuid>") when no id has been bound in the current context,
so log records made outside any tick still carry SOMETHING useful.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

# The var itself. `default=None` means `get()` returns None until we
# bind something. Callers handle that case (they fall back to a stable
# per-process placeholder).
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)

# Stable placeholder when no tick is in flight. Set once at module import.
# Using a uuid keeps it unique across processes and across restarts of
# the same process (so grepping for it is still useful).
_NO_TRACE_ID = f"no-trace-{uuid.uuid4().hex[:8]}"


def new_trace_id() -> str:
    """Mint a fresh trace id and bind it to the current context. Returns
    the new id. Use at the entry of each tick / request / job."""
    tid = uuid.uuid4().hex
    _trace_id.set(tid)
    return tid


def current_trace_id() -> str:
    """Return the trace id bound in the current context, or a stable
    placeholder if none has been bound. Never returns None — log records
    always have a string id to embed."""
    return _trace_id.get() or _NO_TRACE_ID


@contextmanager
def bind_trace(tid: str | None = None) -> Iterator[str]:
    """Bind a trace id for the duration of a `with` block. Used by tests
    and by code that wants to override the current id (e.g. resume a
    paused request). Yields the id actually bound."""
    bound = tid or new_trace_id()
    token = _trace_id.set(bound)
    try:
        yield bound
    finally:
        _trace_id.reset(token)


def _reset_for_tests() -> None:
    """Wipe the contextvar. Only used by tests to ensure isolation.

    Sets the var to None explicitly rather than relying on token reset
    because pytest-asyncio runs fixtures and test bodies in the same
    Task but tests within a module see state from the previous test
    (since the module-level ContextVar persists across event loop
    lifecycles in the same process). Setting None forces `get()` to
    return the default, which `current_trace_id()` translates to the
    stable placeholder."""
    _trace_id.set(None)


class _TraceBinder:
    """Class-based context manager so contextvar set/reset happens in the
    CALLER's context, not a generator's. PEP 568 makes generators capture
    the context at creation time, so `@contextmanager`-decorated functions
    silently no-op the var mutation outside the generator frame — which
    breaks any caller code that expects the var to revert after `with`.

    This class implements the context manager protocol directly so the
    `set` / `reset` calls run in the caller's frame and are visible to
    subsequent `current_trace_id()` reads.

    Implementation note: do NOT call `new_trace_id()` here even though it
    mints a fresh id — it ALSO calls `_trace_id.set()` internally, which
    means by the time we issue our own `set(bound)` we have leaked two
    set tokens and the exit-side reset only restores the inner one,
    leaving the outer one stuck. Mint the uuid locally and set once.
    """

    def __init__(self, tid: str | None = None):
        self._tid = tid
        self._token = None  # type: object | None

    def __enter__(self) -> str:
        bound = self._tid or uuid.uuid4().hex
        # One and only one set. Token lets us reset to whatever was bound
        # BEFORE this `with` block — None, the outer trace, anything.
        self._token = _trace_id.set(bound)
        return bound

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            _trace_id.reset(self._token)
            self._token = None


def bind_trace(tid: str | None = None):
    """Bind a trace id for the duration of a `with` block. Yields the id
    actually bound. Idempotent across nested calls. Works correctly with
    contextvars (unlike `@contextmanager`-decorated generator functions,
    which capture a private context and silently break propagation)."""
    return _TraceBinder(tid)
