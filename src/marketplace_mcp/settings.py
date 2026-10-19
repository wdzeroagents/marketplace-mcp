"""Runtime configuration for the shared server and Ozon account adapter."""

import logging
import os
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class ServerSettings(BaseSettings):
    """Settings shared by the server and every marketplace adapter."""

    model_config = SettingsConfigDict(extra="ignore")

    transport: Literal["stdio", "http", "sse"] = Field(
        default="stdio", validation_alias=AliasChoices("MARKETPLACE_TRANSPORT", "OZON_TRANSPORT")
    )
    host: str = Field(default="0.0.0.0", validation_alias=AliasChoices("MARKETPLACE_HOST", "OZON_HOST"))
    port: int = Field(default=8084, validation_alias=AliasChoices("MARKETPLACE_PORT", "OZON_PORT"))
    allowed_hosts: list[str] = Field(
        default_factory=list, validation_alias=AliasChoices("MARKETPLACE_ALLOWED_HOSTS", "OZON_ALLOWED_HOSTS")
    )
    store_path: Path = Field(
        default=Path("/data/store.db"),
        validation_alias=AliasChoices("MARKETPLACE_STORE_PATH", "OZON_STORE_PATH"),
    )
    idle_seconds: int = Field(
        default=600,
        ge=0,
        validation_alias=AliasChoices(
            "MARKETPLACE_IDLE_SECONDS",
            "OZON_IDLE_SECONDS",
            "WILDBERRIES_IDLE_SECONDS",
            "YANDEX_MARKET_IDLE_SECONDS",
        ),
    )


@cache
def get_server_settings() -> ServerSettings:
    """Read shared settings and warn when a legacy adapter prefix is used."""
    aliases = {
        "OZON_TRANSPORT": "MARKETPLACE_TRANSPORT",
        "OZON_HOST": "MARKETPLACE_HOST",
        "OZON_PORT": "MARKETPLACE_PORT",
        "OZON_ALLOWED_HOSTS": "MARKETPLACE_ALLOWED_HOSTS",
        "OZON_STORE_PATH": "MARKETPLACE_STORE_PATH",
        "OZON_IDLE_SECONDS": "MARKETPLACE_IDLE_SECONDS",
        "WILDBERRIES_IDLE_SECONDS": "MARKETPLACE_IDLE_SECONDS",
        "YANDEX_MARKET_IDLE_SECONDS": "MARKETPLACE_IDLE_SECONDS",
    }
    for legacy, replacement in aliases.items():
        if legacy in os.environ and replacement not in os.environ:
            logger.warning("%s is deprecated; use %s", legacy, replacement)
    return ServerSettings()


class OzonSettings(BaseSettings):
    """Ozon account settings, read from ``OZON_*`` environment variables."""

    model_config = SettingsConfigDict(env_prefix="OZON_", extra="ignore")

    profile_dir: Path = Path("/data/profile")
    """Persistent Chromium profile holding the session, including OzonID state
    that a storageState snapshot cannot carry (IndexedDB, device trust)."""

    profile_backup: Path = Path("/data/profile.backup")
    """Copy of a known-good profile, restored if the live one gets logged out."""

    state_path: Path = Field(
        default=Path("/data/state.json"), validation_alias=AliasChoices("OZON_STATE_PATH", "OZON_STATE")
    )
    """Legacy storageState, imported once to seed a brand-new profile."""

    impersonate: str = "chrome124"
    """curl_cffi TLS-impersonation profile for direct HTTP requests."""

    enable_writes: bool = False
    """Allow account-mutating tools (cart / favorites / lists)."""

    enable_orders: bool = False
    """Allow place_order. Separate from enable_writes: this one spends money."""

    monitor_store: Path = Path("/data/price_history.json")
    """Where favorites price-monitoring snapshots are persisted."""

    request_timeout: float = 30.0
    """Seconds to wait for one HTTP call to Ozon."""

    request_attempts: int = 3
    """How many times one call is attempted before it is reported as failed."""

    retry_backoff_seconds: float = 1.0
    """Base wait between attempts; doubled per attempt and jittered."""

    retry_cap_seconds: float = 20.0
    """Longest server wait before a retry, including a Retry-After request."""

    browser_timeout: float = 60.0
    """Seconds to wait for a browser navigation or a login step."""


@cache
def get_settings() -> OzonSettings:
    """Return account settings for Ozon adapter code."""
    return OzonSettings()
