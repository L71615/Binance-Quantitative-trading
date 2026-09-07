"""Migration idempotency for ai_settings + ai_decision new columns."""
import app.models  # noqa: F401  -- registers tables on Base.metadata
from app.db import Base, engine
from app.migrations import run_all_migrations


def _fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    run_all_migrations(engine)


def test_market_type_column_added_to_ai_settings():
    _fresh_db()
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(engine).get_columns("ai_settings")}
    assert "market_type" in cols


def test_leverage_column_added_to_ai_settings():
    _fresh_db()
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(engine).get_columns("ai_settings")}
    assert "leverage" in cols


def test_margin_type_column_added_to_ai_settings():
    _fresh_db()
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(engine).get_columns("ai_settings")}
    assert "margin_type" in cols


def test_market_type_column_added_to_ai_decision():
    _fresh_db()
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(engine).get_columns("ai_decision")}
    assert "market_type" in cols


def test_leverage_column_added_to_ai_decision():
    _fresh_db()
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(engine).get_columns("ai_decision")}
    assert "leverage" in cols


def test_default_market_type_is_spot():
    """Migrations add columns with NOT NULL DEFAULT 'spot', so a freshly-
    inserted row reads 'spot' without explicit assignment."""
    _fresh_db()
    from app.db import SessionLocal
    from app.models.ai_settings import AISettings, load_or_create
    with SessionLocal() as s:
        row = load_or_create(s)
        assert row.market_type == "spot"
        assert row.margin_type == "ISOLATED"
        assert row.leverage is None


def test_migrations_are_idempotent():
    """Calling run_all_migrations twice must not raise or duplicate."""
    _fresh_db()
    run_all_migrations(engine)  # second call should be a no-op
