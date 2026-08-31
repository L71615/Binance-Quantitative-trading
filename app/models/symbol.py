from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TZDateTime(TypeDecorator):
    """DateTime(timezone=True) wrapper that re-tags naive values as UTC.

    SQLite's driver strips tzinfo on round-trip even when the column is
    declared as timezone-aware, which would break equality comparisons
    against `datetime.now(timezone.utc)`. This decorator restores the
    UTC tzinfo on the way out so callers always get aware datetimes.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: D401
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):  # noqa: D401
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class Symbol(Base):
    __tablename__ = "symbols"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    base: Mapped[str] = mapped_column(String, nullable=False)
    quote: Mapped[str] = mapped_column(String, nullable=False)
    min_qty: Mapped[float] = mapped_column(Float, nullable=False)
    tick_size: Mapped[float] = mapped_column(Float, nullable=False)
    step_size: Mapped[float] = mapped_column(Float, nullable=False)
    min_notional: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
