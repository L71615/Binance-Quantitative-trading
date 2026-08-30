"""Centralized configuration. Reads env vars for dev; keyring is the
canonical store in production (see app/crypto_store.py)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BINANCE_", extra="ignore")

    testnet: bool = Field(default=True, alias="BINANCE_TESTNET")
    api_key: str = Field(default="", alias="BINANCE_API_KEY")
    api_secret: str = Field(default="", alias="BINANCE_API_SECRET")
    base_url: str = Field(default="https://testnet.binance.vision", alias="BINANCE_BASE_URL_OVERRIDE")

    @property
    def binance_testnet(self) -> bool:
        return self.testnet

    @property
    def binance_api_key(self) -> str:
        return self.api_key

    @property
    def binance_api_secret(self) -> str:
        return self.api_secret


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
