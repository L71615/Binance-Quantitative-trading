import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GridStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class Grid(Base):
    __tablename__ = "grids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    lower_price: Mapped[float] = mapped_column(Float, nullable=False)
    upper_price: Mapped[float] = mapped_column(Float, nullable=False)
    grid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    grid_mode: Mapped[str] = mapped_column(String, default="arithmetic", nullable=False)
    total_quote_amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[GridStatus] = mapped_column(
        Enum(GridStatus, native_enum=False), default=GridStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)