"""Background scheduler that drives AITraderService.tick() at poll_interval_sec.

F1.5: until this module landed, AITraderService had a tick() method but no
caller. /start flipped status to "running" but nothing actually polled —
the bot never ran 24h. This scheduler is the missing link between the
state machine and real on-exchange behavior.

Design:
  - One asyncio task per process, started in main.py lifespan.
  - The task is gated on AISettings.status == "running" — when paused /
    stopped / error, it just sleeps and re-checks. tick() itself also
    short-circuits when status != running (defense in depth).
  - Single tick wraps trader.tick() in asyncio.wait_for with a 30s
    timeout so a runaway tick cannot starve the loop.
  - Loop exceptions are logged, never propagated — a transient failure
    must not kill the process.
  - Shutdown sets _stopping=True; the loop notices and exits cleanly.
  - The interval is re-read from AISettings every iteration, so changing
    poll_interval_sec via /api/ai-trader/settings takes effect at the next
    tick without a restart.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.db import SessionLocal
from app.models.ai_settings import load_or_create

if TYPE_CHECKING:
    from app.services.ai_trader.service import AITraderService

logger = logging.getLogger(__name__)

# Per-symbol tick timeout. A normal tick is sub-second; anything past 30s
# indicates a hung LLM or broker call. Raising it past 60s would let one
# bad tick swallow the whole poll_interval budget and silently drop ticks.
_TICK_TIMEOUT_SEC = 30.0

# Floor and ceiling for poll_interval_sec. The settings table accepts >=1,
# but a 1-second poll would hammer the exchange. We refuse to run faster
# than 5s even if the user writes 1. The ceiling is a sanity guard against
# runaway values; the user-facing default is 60.
_MIN_POLL_INTERVAL_SEC = 5
_MAX_POLL_INTERVAL_SEC = 3600


class AITraderScheduler:
    """Owns the single background task that polls AITraderService.tick()."""

    def __init__(self, trader: "AITraderService"):
        self._trader = trader
        self._task: asyncio.Task | None = None
        self._stopping = False

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._loop(), name="ai-trader-scheduler")
        logger.info("ai trader scheduler started")

    async def stop(self) -> None:
        self._stopping = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None
        logger.info("ai trader scheduler stopped")

    def _read_poll_interval(self) -> int:
        """Re-read poll_interval_sec every iteration so /settings changes
        take effect at the next tick without a process restart."""
        try:
            with SessionLocal() as s:
                row = load_or_create(s)
                interval = int(row.poll_interval_sec or 60)
        except Exception:
            logger.exception("scheduler: failed to read poll_interval_sec; using 60")
            interval = 60
        return max(_MIN_POLL_INTERVAL_SEC, min(interval, _MAX_POLL_INTERVAL_SEC))

    def _is_running(self) -> bool:
        """Read-only check of status — drives the loop's gate."""
        try:
            with SessionLocal() as s:
                row = load_or_create(s)
                return row.status == "running"
        except Exception:
            logger.exception("scheduler: status read failed; treating as not running")
            return False

    async def _loop(self) -> None:
        # One-second sleep granularity so a stop() request interrupts quickly
        # even when poll_interval is 300s. The loop checks _stopping every
        # second; the actual tick fires once per poll_interval.
        while not self._stopping:
            interval = self._read_poll_interval()
            # Sleep in 1s slices so cancellation/stop is responsive.
            slept = 0.0
            while slept < interval and not self._stopping:
                step = min(1.0, interval - slept)
                await asyncio.sleep(step)
                slept += step
            if self._stopping:
                break

            if not self._is_running():
                # Not running — skip this tick but keep polling. The user
                # may resume at any moment via /api/ai-trader/start.
                continue

            try:
                await asyncio.wait_for(
                    self._trader.tick(), timeout=_TICK_TIMEOUT_SEC
                )
            except asyncio.TimeoutError:
                # One tick hung past 30s. Log and keep going — the next tick
                # will try again. We do NOT increment LLM error counts here:
                # that's the tick's own _maybe_trip_after_tick concern.
                logger.error(
                    "ai trader tick exceeded %.0fs timeout; skipping",
                    _TICK_TIMEOUT_SEC,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                # Anything else (DB blip, programming bug) — log and keep the
                # loop alive. Killing the loop on a transient exception would
                # silently disable 24h autonomy.
                logger.exception("ai trader tick raised; continuing")


def make_scheduler(trader: "AITraderService") -> AITraderScheduler:
    """Factory used by main.py lifespan — the trader singleton must already be
    wired (broker + llm set or not) by the time we instantiate the scheduler."""
    return AITraderScheduler(trader)
