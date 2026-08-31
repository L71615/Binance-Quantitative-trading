from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Symbol(Base):
    __tablename__ = "symbols"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    base: Mapped[str] = mapped_column(String, nullable=False)
    quote: Mapped[str] = mapped_column(String, nullable=False)
    min_qty: Mapped[float] = mapped_column(Float, nullable=False)
    tick_size: Mapped[float] = mapped_column(Float, nullable=False)
    step_size: Mapped[float] = mapped_column(Float, nullable=False)
    min_notional: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
