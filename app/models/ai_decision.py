"""Audit row for one AI Trader tick. Spec §6."""
from __future__ import annotations

from datetime import datetime, UTC

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AIDecision(Base):
    __tablename__ = "ai_decision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    market_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response: Mapped[str] = mapped_column(Text, nullable=False)
    parsed: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    guard_results: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False, index=True)
    order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    order_status: Mapped[str | None] = mapped_column(String, nullable=True)
    filled_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    # `is_paper` partitions paper-trading audit rows from live. Required so the
    # daily-loss / daily-trades counters in `_compute_today_counters` (which
    # query this table) do not bleed paper P&L into the live guard budget —
    # paper losses must never trip the live daily_loss_cap. Indexed because
    # every tick's counter query filters by it. Default False keeps live
    # rows (the historical majority) out of any future paper-only scan.
    # SQLAlchemy maps Boolean to INTEGER on SQLite (0/1), which is what the
    # ALTER TABLE migration below also produces, so reads stay consistent.
    is_paper: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        server_default="0",
    )
    market_type: Mapped[str] = mapped_column(
        String, default="spot", nullable=False, index=True
    )
    leverage: Mapped[int | None] = mapped_column(Integer, nullable=True)
