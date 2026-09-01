"""Singleton row (id=1) holding AI Trader state + risk caps."""
from __future__ import annotations

import json
from datetime import datetime, UTC

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AISettings(Base):
    __tablename__ = "ai_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[str] = mapped_column(String, default="idle", nullable=False)
    status_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    armed_for_live_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    max_order_quote_usdt: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)
    max_position_per_symbol_usdt: Mapped[float] = mapped_column(
        Float, default=500.0, nullable=False
    )
    daily_loss_cap_usdt: Mapped[float] = mapped_column(Float, default=-30.0, nullable=False)
    daily_max_trades: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    symbols: Mapped[str] = mapped_column(String, default='["BTCUSDT"]', nullable=False)
    poll_interval_sec: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    @property
    def symbol_list(self) -> list[str]:
        try:
            return json.loads(self.symbols)
        except (json.JSONDecodeError, TypeError):
            return []

    @symbol_list.setter
    def symbol_list(self, value: list[str]) -> None:
        self.symbols = json.dumps(value)


def load_or_create(session) -> AISettings:
    """Return the singleton row, creating it on first call."""
    s = session.get(AISettings, 1)
    if s is None:
        s = AISettings(id=1)
        session.add(s)
        session.commit()
        session.refresh(s)
    return s


def save(session, settings: AISettings) -> AISettings:
    """Persist changes to the singleton row, bumping updated_at."""
    settings.updated_at = datetime.now(UTC)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings
