"""Aggregate import: register all ORM models with Base.metadata.

Any module that touches the schema (tests, FastAPI startup, the engine)
should `from app.models import Grid  # noqa` (or similar) so all sibling
tables are registered before `Base.metadata.create_all()` is invoked.
"""
from app.models.app_state import AppState  # noqa: F401
from app.models.grid import Grid  # noqa: F401
from app.models.kline import KLine  # noqa: F401
from app.models.order import Order  # noqa: F401
from app.models.setting import Setting  # noqa: F401
from app.models.symbol import Symbol  # noqa: F401
from app.models.trade import Trade  # noqa: F401
