"""Encrypted local secrets via OS keyring (Windows Credential Manager
on this platform). Slug namespaced so multiple local bots do not collide."""
from __future__ import annotations

import keyring
import keyring.errors

# Renamed from "binance-spot-grid-bot" (2026-09-07) when futures support
# was added. Binance Spot + USDⓈ-M Futures share the same API key+secret,
# so they should share one keyring namespace.
SERVICE_NAME = "binance-trading-bot"


def save_secret(slug: str, value: str) -> None:
    keyring.set_password(SERVICE_NAME, slug, value)


def load_secret(slug: str) -> str | None:
    try:
        return keyring.get_password(SERVICE_NAME, slug)
    except keyring.errors.KeyringError:
        return None


def delete_secret(slug: str) -> None:
    try:
        keyring.delete_password(SERVICE_NAME, slug)
    except keyring.errors.PasswordDeleteError:
        pass
