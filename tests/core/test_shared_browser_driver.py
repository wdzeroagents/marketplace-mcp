import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from marketplace_mcp.adapters.ozon.session.transport import OzonSession
from marketplace_mcp.adapters.wildberries.session import WildberriesSession
from marketplace_mcp.adapters.yandex_market.session import YandexMarketSession
from marketplace_mcp.core import browser, dependencies


def test_get_playwright_starts_one_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = Mock()
    start = Mock(return_value=driver)
    monkeypatch.setattr(browser, "sync_playwright", lambda: Mock(start=start))
    browser.get_playwright.cache_clear()
    try:
        assert browser.get_playwright() is driver
        assert browser.get_playwright() is driver
        start.assert_called_once_with()
    finally:
        browser.get_playwright.cache_clear()


def test_worker_cleanup_runs_on_session_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    callbacks = []
    worker_names: list[str] = []
    monkeypatch.setattr(dependencies.threading, "_register_atexit", callbacks.append)
    with ThreadPoolExecutor(max_workers=1) as executor:
        monkeypatch.setattr(dependencies, "get_executor", lambda: executor)
        dependencies.register_worker_cleanup(lambda: worker_names.append(threading.current_thread().name))

        assert len(callbacks) == 1
        callbacks[0]()

    assert len(worker_names) == 1
    assert worker_names[0] != threading.current_thread().name


@pytest.mark.parametrize(
    ("session", "close_method"),
    [
        (OzonSession, "_close_browser"),
        (WildberriesSession, "_close_browser"),
        (YandexMarketSession, "close"),
    ],
)
def test_adapter_closes_only_its_context(session: type, close_method: str) -> None:
    instance = session()
    context = instance._context = Mock()
    driver = instance._playwright = Mock()

    getattr(instance, close_method)()

    context.close.assert_called_once_with()
    driver.stop.assert_not_called()
