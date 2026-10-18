"""Browser-owned credentials stay out of the MCP call surface."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from marketplace_mcp.adapters.yandex_market import session


class FakePage:
    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.url = ""
        self.result = result or {"status": 200, "text": '{"results": []}'}
        self.visited: list[str] = []
        self.script = ""
        self.argument: dict[str, Any] = {}

    def set_default_timeout(self, timeout: float) -> None:
        self.timeout = timeout

    def goto(self, url: str, **_: Any) -> None:
        self.url = url
        self.visited.append(url)

    def evaluate(self, script: str, argument: dict[str, Any]) -> dict[str, Any]:
        self.script = script
        self.argument = argument
        return self.result


def configured(result: dict[str, Any] | None = None) -> tuple[session.YandexMarketSession, FakePage]:
    client = session.YandexMarketSession(session.YandexMarketSettings(profile_dir=Path("yandex-profile-test")))
    page = FakePage(result)
    client._page = page
    return client, page


def test_request_uses_browser_cookies_and_fresh_page_sk() -> None:
    client, page = configured()
    client.page("active")
    assert page.visited == [session.HOME + "/my/orders"]
    assert page.argument == {
        "endpoint": session.RESOLVER,
        "payload": {"params": [{"filter": "ACTIVE", "size": 20}], "path": "/my/orders"},
    }
    assert 'credentials: "same-origin"' in page.script
    assert "document.documentElement.outerHTML" in page.script
    assert "Session_id" not in page.script
    client.page("completed", "cursor")
    assert page.visited[-1] == session.HOME + "/my/orders?filter=COMPLETED"
    assert page.argument["payload"]["params"][0] == {"filter": "COMPLETED", "size": 20, "pageToken": "cursor"}


@pytest.mark.parametrize(
    ("result", "code"),
    [
        ({"status": 401, "text": ""}, "session_expired"),
        ({"status": 403, "text": ""}, "session_expired"),
        ({"status": 429, "text": ""}, "rate_limited"),
        ({"status": 502, "text": ""}, "upstream_unavailable"),
        ({"status": 0, "error": "session_parameter_missing"}, "session_expired"),
        ({"status": 0, "error": "request_failed"}, "upstream_unavailable"),
    ],
)
def test_browser_failures_are_coded(result: dict[str, Any], code: str) -> None:
    client, _ = configured(result)
    with pytest.raises(session.YandexMarketError, match=code):
        client.page("active")


def test_invalid_json_is_not_empty() -> None:
    client, _ = configured({"status": 200, "text": "not-json"})
    with pytest.raises(session.YandexMarketError, match="invalid JSON"):
        client.page("active")


def test_open_login_opens_orders_in_persistent_browser() -> None:
    client, page = configured()
    status = client.open_login()
    assert page.visited == [session.HOME + "/my/orders"]
    assert status.browser_open is True
    assert status.signed_in is False
    assert "sign in" in (status.detail or "").lower()


def test_status_uses_resolver_to_verify_authentication() -> None:
    client, _ = configured()
    assert client.status().signed_in is True

    expired, _ = configured({"status": 403, "text": ""})
    status = expired.status()
    assert status.signed_in is False
    assert status.browser_open is True
    assert "open_login" in (status.detail or "")


def test_close_stops_context_and_playwright() -> None:
    client, _ = configured()
    context = Mock()
    playwright = Mock()
    client._context = context
    client._playwright = playwright
    client.close()
    context.close.assert_called_once_with()
    playwright.stop.assert_called_once_with()
    assert client._page is None
