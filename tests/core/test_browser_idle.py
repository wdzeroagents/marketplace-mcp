from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from marketplace_mcp.adapters.ozon.session import transport as ozon_transport
from marketplace_mcp.adapters.wildberries import session as wildberries_session
from marketplace_mcp.adapters.wildberries.session import WildberriesSettings
from marketplace_mcp.adapters.yandex_market import session as yandex_session
from marketplace_mcp.adapters.yandex_market.session import YandexMarketSettings


def test_ozon_closes_only_its_idle_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ozon_transport.OzonSession()
    old_context = client._context = Mock()
    client._page = Mock()
    driver = client._playwright = Mock()
    http = client._http = Mock()
    client._browser_last_used = 100
    monkeypatch.setattr(ozon_transport, "get_server_settings", lambda: SimpleNamespace(idle_seconds=10))
    monkeypatch.setattr(ozon_transport.time, "monotonic", lambda: 111)
    launch = Mock(side_effect=lambda: setattr(client, "_page", Mock()))
    monkeypatch.setattr(client, "_launch_browser", launch)

    client._ensure_browser()

    old_context.close.assert_called_once_with()
    launch.assert_called_once_with()
    assert client._http is http
    driver.stop.assert_not_called()


@pytest.mark.parametrize(
    ("module", "session_factory", "settings_factory"),
    [
        (
            wildberries_session,
            wildberries_session.WildberriesSession,
            lambda path: WildberriesSettings(profile_dir=path / "wb-profile"),
        ),
        (
            yandex_session,
            yandex_session.YandexMarketSession,
            lambda path: YandexMarketSettings(profile_dir=path / "ym-profile"),
        ),
    ],
)
def test_marketplace_reopens_its_browser_after_idle(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    session_factory: Any,
    settings_factory: Any,
    tmp_path: Path,
) -> None:
    client = session_factory(settings=settings_factory(tmp_path))
    monkeypatch.setattr(module, "get_server_settings", lambda: SimpleNamespace(idle_seconds=10))
    old_context = client._context = Mock()
    client._page = Mock()
    driver = client._playwright = Mock()
    client._browser_last_used = 100
    monkeypatch.setattr(module.time, "monotonic", lambda: 111)
    new_context = Mock()
    new_context.pages = [Mock()]
    driver.chromium.launch_persistent_context.return_value = new_context
    monkeypatch.setattr(module, "get_playwright", lambda: driver)

    client._ensure_browser()

    old_context.close.assert_called_once_with()
    driver.chromium.launch_persistent_context.assert_called_once()
    assert client._context is new_context
    assert client._page is not None
    driver.stop.assert_not_called()
