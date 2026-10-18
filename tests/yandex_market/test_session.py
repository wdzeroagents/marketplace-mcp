"""Browser-owned credentials stay out of the MCP call surface."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Self
from unittest.mock import Mock

import pytest

from marketplace_mcp.adapters.yandex_market import session


class FakePage:
    def __init__(self, result: Any = None) -> None:
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

    def evaluate(self, script: str, argument: dict[str, Any] | None = None) -> Any:
        self.script = script
        self.argument = argument or {}
        return self.result

    def title(self) -> str:
        return "Yandex Market"


class FakeResponseInfo:
    def __init__(self, response: Any) -> None:
        self.value = response

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class InteractivePage(FakePage):
    def __init__(self) -> None:
        super().__init__()
        self.favorite = False
        self.cart_contains = False
        self.clicked: list[str] = []

    def evaluate(self, script: str, argument: dict[str, Any] | None = None) -> Any:
        if script == session._FAVORITE_STATE_SCRIPT:
            return {"favorite": self.favorite}
        if script == session._CART_CONTAINS_SCRIPT:
            return self.cart_contains
        return super().evaluate(script, argument)

    def expect_response(self, predicate: Any) -> FakeResponseInfo:
        for endpoint in (
            session.WISHLIST_ADD_ENDPOINT,
            session.WISHLIST_DELETE_ENDPOINT,
            session.CART_ADD_ENDPOINT,
        ):
            response = SimpleNamespace(url=session.HOME + endpoint, status=200)
            if predicate(response):
                return FakeResponseInfo(response)
        raise AssertionError("Unexpected response predicate")

    def locator(self, selector: str) -> Any:
        page = self

        class Locator:
            @property
            def first(self) -> Any:
                return self

            def click(self) -> None:
                page.clicked.append(selector)
                if selector == 'button[data-auto="wishlist"]':
                    page.favorite = not page.favorite
                elif selector == 'button[data-auto="cartButton"]':
                    page.cart_contains = True

        return Locator()


def configured(result: Any = None) -> tuple[session.YandexMarketSession, FakePage]:
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


def test_search_encodes_query_and_limits_frontend_results() -> None:
    client, page = configured([{"product_id": "123456"}])

    rows = client.search_page("чай & кофе", 1)

    assert rows == [{"product_id": "123456"}]
    assert page.visited == [session.HOME + "/search?text=%D1%87%D0%B0%D0%B9%20%26%20%D0%BA%D0%BE%D1%84%D0%B5"]
    assert page.argument == {"limit": 1}
    assert 'data-auto="snippet-link"' in page.script


def test_product_page_only_accepts_clean_market_card_path() -> None:
    client, page = configured({"product_id": "123456", "title": "Чай"})

    result = client.product_page("/card/chay/123456")

    assert result == {"product_id": "123456", "title": "Чай"}
    assert page.visited == [session.HOME + "/card/chay/123456"]
    assert "application/ld+json" in page.script

    with pytest.raises(ValueError, match="clean Yandex Market product-card path"):
        client.product_page("/card/../123456")


def test_favorite_and_cart_actions_use_first_party_controls_and_read_back() -> None:
    client = session.YandexMarketSession(session.YandexMarketSettings(profile_dir=Path("yandex-profile-test")))
    page = InteractivePage()
    client._page = page

    assert client.set_product_favorite("/card/chay/123456", add=True) is True
    assert page.favorite is True
    assert client.add_product_to_cart("/card/chay/123456", "123456", "Чай") is True
    assert page.cart_contains is True
    assert page.clicked == ['button[data-auto="wishlist"]', 'button[data-auto="cartButton"]']


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "session_expired"), (403, "session_expired"), (429, "rate_limited"), (500, "upstream_unavailable")],
)
def test_mutation_http_errors_are_coded(status: int, code: str) -> None:
    with pytest.raises(session.YandexMarketError, match=code):
        session.YandexMarketSession._check_mutation_status(status)
