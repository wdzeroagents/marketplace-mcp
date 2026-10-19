from collections.abc import Iterator
from pathlib import Path

import pytest

from marketplace_mcp.settings import get_server_settings


@pytest.fixture
def clear_server_settings_cache() -> Iterator[None]:
    get_server_settings.cache_clear()
    yield
    get_server_settings.cache_clear()


def test_shared_settings_keep_legacy_ozon_values(
    monkeypatch: pytest.MonkeyPatch, clear_server_settings_cache: None
) -> None:
    monkeypatch.setenv("OZON_PORT", "9000")
    monkeypatch.setenv("OZON_STORE_PATH", "old-store.db")

    settings = get_server_settings()

    assert settings.port == 9000
    assert settings.store_path == Path("old-store.db")


def test_marketplace_prefix_takes_precedence_over_legacy(
    monkeypatch: pytest.MonkeyPatch, clear_server_settings_cache: None
) -> None:
    monkeypatch.setenv("MARKETPLACE_PORT", "8085")
    monkeypatch.setenv("OZON_PORT", "9000")

    assert get_server_settings().port == 8085


def test_one_shared_idle_timeout_accepts_legacy_adapter_names(
    monkeypatch: pytest.MonkeyPatch, clear_server_settings_cache: None
) -> None:
    monkeypatch.setenv("WILDBERRIES_IDLE_SECONDS", "120")

    assert get_server_settings().idle_seconds == 120

    monkeypatch.setenv("MARKETPLACE_IDLE_SECONDS", "300")
    get_server_settings.cache_clear()
    assert get_server_settings().idle_seconds == 300
