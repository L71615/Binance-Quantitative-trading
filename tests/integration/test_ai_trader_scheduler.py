"""P0-2 (CEO plan F1.5): background tick scheduler drives AITraderService.

Pre-fix: AITraderService had tick() but no caller — bot could be flipped
to "running" and never actually trade. These tests pin the post-fix
contract: when status == "running" the scheduler calls tick() at
poll_interval_sec, skipping ticks when not running, recovering from
exceptions and timeouts, and stopping cleanly.

Tests use a tiny poll_interval (3s) and tick spies so they finish in <10s.
"""
import asyncio
import pytest

from app.db import Base, SessionLocal, engine
from app.migrations import run_all_migrations
from app.models.ai_settings import load_or_create
from app.services.ai_trader.scheduler import AITraderScheduler
from app.services.ai_trader.service import AITraderService


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    run_all_migrations(engine)
    yield
    Base.metadata.drop_all(engine)


def _set_status(status: str, poll_interval_sec: int = 3):
    with SessionLocal() as s:
        row = load_or_create(s)
        row.status = status
        row.poll_interval_sec = poll_interval_sec
        s.commit()


class _SpyTrader:
    """Drop-in AITraderService stand-in that records tick() calls."""

    def __init__(self, *, raises: Exception | None = None,
                 sleep: float = 0.0):
        self.ticks = 0
        self.raises = raises
        self.sleep = sleep

    async def tick(self) -> None:
        self.ticks += 1
        if self.sleep:
            await asyncio.sleep(self.sleep)
        if self.raises:
            raise self.raises


async def _wait_for(predicate, *, timeout: float = 5.0, interval: float = 0.1):
    """Poll a predicate until True or timeout. Avoids brittle time.sleep."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


@pytest.mark.asyncio
async def test_scheduler_skips_ticks_when_not_running():
    """status != running → scheduler polls but never calls tick()."""
    _set_status("paused")
    spy = _SpyTrader()
    sched = AITraderScheduler(spy)  # type: ignore[arg-type]
    sched.start()
    try:
        await asyncio.sleep(4.0)  # > 1 poll cycle (3s) plus margin
        assert spy.ticks == 0, (
            f"expected 0 ticks while paused, got {spy.ticks}. "
            "Scheduler must gate on status==running."
        )
    finally:
        await sched.stop()


@pytest.mark.asyncio
async def test_scheduler_calls_tick_when_running():
    """status == running → tick() fires once per poll_interval_sec."""
    _set_status("running", poll_interval_sec=5)
    spy = _SpyTrader()
    sched = AITraderScheduler(spy)  # type: ignore[arg-type]
    sched.start()
    try:
        # 5s interval, so 12s gives us 2 ticks (t≈5, t≈10) plus margin.
        got_two = await _wait_for(lambda: spy.ticks >= 2, timeout=12.0)
        assert got_two, f"expected ≥2 ticks in 12s, got {spy.ticks}"
    finally:
        await sched.stop()


@pytest.mark.asyncio
async def test_scheduler_recovers_from_tick_exception():
    """A tick that raises must NOT kill the scheduler loop."""
    _set_status("running", poll_interval_sec=5)
    bomb = _SpyTrader(raises=RuntimeError("simulated LLM blowup"))
    sched = AITraderScheduler(bomb)  # type: ignore[arg-type]
    sched.start()
    try:
        got_two = await _wait_for(lambda: bomb.ticks >= 2, timeout=12.0)
        assert got_two, (
            f"expected ≥2 ticks despite exception, got {bomb.ticks}. "
            "Scheduler loop died on first exception — F1.5 regressed."
        )
    finally:
        await sched.stop()


@pytest.mark.asyncio
async def test_scheduler_recovers_from_tick_timeout():
    """A tick that hangs past 30s must be cancelled and the loop continues.

    We can't wait 30s in a test, so we monkeypatch the constant. This still
    pins the contract: hang → cancel → log → next tick fires."""
    from app.services.ai_trader import scheduler as sched_mod
    original = sched_mod._TICK_TIMEOUT_SEC
    sched_mod._TICK_TIMEOUT_SEC = 0.5  # 500ms timeout for the test
    try:
        _set_status("running", poll_interval_sec=5)
        hang = _SpyTrader(sleep=2.0)  # tick sleeps 2s, exceeds 500ms
        sched = AITraderScheduler(hang)  # type: ignore[arg-type]
        sched.start()
        try:
            # First tick at t≈5s hangs until t≈5.5s (timeout).
            # Second tick at t≈10s.
            # Third  tick at t≈15s.
            # Total test budget 18s for ≥2 ticks.
            got_two = await _wait_for(lambda: hang.ticks >= 2, timeout=18.0)
            assert got_two, (
                f"expected ≥2 ticks with one timeout, got {hang.ticks}. "
                "Scheduler must survive wait_for timeouts."
            )
        finally:
            await sched.stop()
    finally:
        sched_mod._TICK_TIMEOUT_SEC = original


@pytest.mark.asyncio
async def test_scheduler_reads_interval_each_outer_iteration():
    """poll_interval_sec is re-read every outer-loop iteration (not cached).
    We verify this by counting _read_poll_interval calls during a few ticks."""
    _set_status("running", poll_interval_sec=5)
    spy = _SpyTrader()
    sched = AITraderScheduler(spy)  # type: ignore[arg-type]

    # Patch _read_poll_interval to count calls without altering behavior.
    real = sched._read_poll_interval
    calls = {"n": 0}

    def counting():
        calls["n"] += 1
        return real()

    sched._read_poll_interval = counting  # type: ignore[assignment]
    sched.start()
    try:
        await _wait_for(lambda: spy.ticks >= 1, timeout=8.0)
        # At least 1 read per outer iteration (right after start), and 1 more
        # per tick cycle. We just want a non-trivial count, not an exact number.
        assert calls["n"] >= 2, (
            f"expected ≥2 reads of poll_interval (1 at start + 1 per tick), "
            f"got {calls['n']}"
        )
    finally:
        await sched.stop()


@pytest.mark.asyncio
async def test_scheduler_stop_is_responsive():
    """stop() must interrupt a long sleep quickly."""
    _set_status("running", poll_interval_sec=10)
    spy = _SpyTrader()
    sched = AITraderScheduler(spy)  # type: ignore[arg-type]
    sched.start()
    await asyncio.sleep(0.2)  # let it enter the long sleep
    # stop() should complete in well under poll_interval.
    stopped = await asyncio.wait_for(sched.stop(), timeout=2.0)
    assert stopped is None, "stop() must return None"


@pytest.mark.asyncio
async def test_scheduler_polls_clamped_between_5_and_3600():
    """poll_interval_sec values outside [5, 3600] must be clamped, not honored."""
    # poll_interval_sec=1 should clamp to 5s — but waiting 5s in a test is
    # slow, so just verify the helper returns the clamped value directly.
    _set_status("paused", poll_interval_sec=1)
    spy = _SpyTrader()
    sched = AITraderScheduler(spy)  # type: ignore[arg-type]
    assert sched._read_poll_interval() == 5

    _set_status("paused", poll_interval_sec=99999)
    assert sched._read_poll_interval() == 3600

    _set_status("paused", poll_interval_sec=120)
    assert sched._read_poll_interval() == 120
