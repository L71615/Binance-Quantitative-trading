"""ReplayLLM: replay stored raw_response strings from AIDecision.

CEO plan P0-5 (OV-B): replaying historical decisions is the cheap path
to backtesting. Instead of refactoring tick() into a pure function
(multi-day surgery), we replace the LLM client with one that returns
recorded decisions. Cost: $0 in tokens, ~$0.0001 per replay in DB
query. Live tests that already produced rows in AIDecision give us the
replay material for free.

Usage:
    rl = ReplayLLM.from_ai_decisions(rows=[r1, r2, ...])
    raw = await rl.chat(messages)  # returns r1.raw_response, then r2, ...

The replay DOES NOT validate that `messages` matches what produced the
recorded response. We trust the operator ran the same prompt structure
during the source period; if they didn't, the backtest is invalid and
the report will show it (guards will reject everything).

Why iterator-based, not random-access: live AIDecision rows arrive in
chronological order, and backtest replay walks them in the same order.
The iterator pattern keeps the interface tiny (just `chat()`).
"""
from __future__ import annotations

from typing import Iterable, Iterator

from app.services.llm import LLMError


class ReplayLLM:
    """Returns stored raw_response strings in order. No network calls.

    When the queue is exhausted, raises LLMError so the backtest runner
    can stop the loop and emit a "ran out of replay material" diagnostic.
    The alternative (loop forever returning the last row) would let a
    bad backtest produce thousands of identical decisions and silently
    skew the metrics.
    """

    def __init__(self, rows: Iterable):
        self._iter: Iterator = iter(rows)
        # Map[hash(messages) -> raw_response] would let us be strict about
        # prompt matching, but messages are large blobs and the contract
        # is "trust the operator ran the same prompt". We just walk.
        self.calls = 0
        self.exhausted_at: int | None = None

    @classmethod
    def from_ai_decisions(cls, rows) -> "ReplayLLM":
        """Build a replay from AIDecision rows in chronological order."""
        return cls(sorted(rows, key=lambda r: r.ts))

    async def chat(self, messages, **kwargs) -> str:
        if self.exhausted_at is not None:
            raise LLMError(
                f"replay_exhausted: served {self.exhausted_at} responses; "
                "backtest period longer than recorded material"
            )
        try:
            row = next(self._iter)
        except StopIteration:
            self.exhausted_at = self.calls
            raise LLMError(
                f"replay_exhausted: served {self.calls} responses; "
                "backtest period longer than recorded material"
            )
        self.calls += 1
        return row.raw_response
