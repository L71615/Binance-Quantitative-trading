"""Idempotent SQLite migrations applied at app startup.

The repo does not use alembic yet. Migrations here are intentionally tiny and
additive: each function checks whether the column already exists (via PRAGMA)
and only alters the table if not. Re-running the function on an already-migrated
DB is a no-op.

Run order from main.py lifespan is: `_migrate_ai_decision_is_paper()` first,
then `Base.metadata.create_all(engine)` so brand-new installs get the column
from the model definition and existing installs get it from this script.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)


def _has_column(engine: Engine, table: str, column: str) -> bool:
    """PRAGMA table_info — returns True iff `column` exists on `table`."""
    with engine.connect() as conn:
        rows = conn.execute(text(f'PRAGMA table_info("{table}")')).fetchall()
    # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
    return any(r[1] == column for r in rows)


def _migrate_ai_decision_is_paper(engine: Engine) -> None:
    """Add `is_paper` column to ai_decision if missing.

    Background: paper-trading rows must not feed the live daily_loss /
    daily_trades counters, which query the ai_decision table. Pre-migration
    audits had no is_paper flag, so paper P&L silently tripped the live
    daily_loss_cap. See CEO plan OV-C.
    """
    if _has_column(engine, "ai_decision", "is_paper"):
        log.info("migration: ai_decision.is_paper already present, skipping")
        return
    log.info("migration: adding ai_decision.is_paper (default 0)")
    with engine.begin() as conn:
        conn.execute(
            text(
                'ALTER TABLE "ai_decision" '
                'ADD COLUMN is_paper INTEGER NOT NULL DEFAULT 0'
            )
        )
    # Index creation is separate — `CREATE INDEX IF NOT EXISTS` is idempotent.
    with engine.begin() as conn:
        conn.execute(
            text(
                'CREATE INDEX IF NOT EXISTS "ix_ai_decision_is_paper" '
                'ON "ai_decision" (is_paper)'
            )
        )
    log.info("migration: ai_decision.is_paper added")


def _migrate_ai_settings_market_type(engine: Engine) -> None:
    """Add market_type column to ai_settings. Idempotent."""
    if _has_column(engine, "ai_settings", "market_type"):
        return
    log.info("migration: adding ai_settings.market_type")
    with engine.begin() as conn:
        conn.execute(text(
            'ALTER TABLE "ai_settings" ADD COLUMN market_type VARCHAR NOT NULL DEFAULT \'spot\''
        ))


def _migrate_ai_settings_leverage(engine: Engine) -> None:
    """Add leverage column to ai_settings. NULL for spot rows."""
    if _has_column(engine, "ai_settings", "leverage"):
        return
    log.info("migration: adding ai_settings.leverage")
    with engine.begin() as conn:
        conn.execute(text(
            'ALTER TABLE "ai_settings" ADD COLUMN leverage INTEGER'
        ))


def _migrate_ai_settings_margin_type(engine: Engine) -> None:
    """Add margin_type column to ai_settings. Default 'ISOLATED'."""
    if _has_column(engine, "ai_settings", "margin_type"):
        return
    log.info("migration: adding ai_settings.margin_type")
    with engine.begin() as conn:
        conn.execute(text(
            'ALTER TABLE "ai_settings" ADD COLUMN margin_type VARCHAR NOT NULL DEFAULT \'ISOLATED\''
        ))


def _migrate_ai_decision_market_type(engine: Engine) -> None:
    """Add market_type column to ai_decision for audit-row market tagging."""
    if _has_column(engine, "ai_decision", "market_type"):
        return
    log.info("migration: adding ai_decision.market_type")
    with engine.begin() as conn:
        conn.execute(text(
            'ALTER TABLE "ai_decision" ADD COLUMN market_type VARCHAR NOT NULL DEFAULT \'spot\''
        ))
    with engine.begin() as conn:
        conn.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_ai_decision_market_type" '
            'ON "ai_decision" (market_type)'
        ))


def _migrate_ai_decision_leverage(engine: Engine) -> None:
    """Add leverage column to ai_decision. NULL for spot rows."""
    if _has_column(engine, "ai_decision", "leverage"):
        return
    log.info("migration: adding ai_decision.leverage")
    with engine.begin() as conn:
        conn.execute(text(
            'ALTER TABLE "ai_decision" ADD COLUMN leverage INTEGER'
        ))


def run_all_migrations(engine: Engine) -> None:
    """Run every migration in order. Add new ones to the bottom."""
    _migrate_ai_decision_is_paper(engine)
    _migrate_ai_settings_market_type(engine)
    _migrate_ai_settings_leverage(engine)
    _migrate_ai_settings_margin_type(engine)
    _migrate_ai_decision_market_type(engine)
    _migrate_ai_decision_leverage(engine)
