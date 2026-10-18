from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from marketplace_mcp.adapters.wildberries.session import (
    WildberriesSession,
    WildberriesSettings,
    WildberriesSignedOutError,
)
from marketplace_mcp.core.errors import ErrorCode


class FakePage:
    def __init__(self, token: str | None = None) -> None:
        self.url = "about:blank"
        self.token = token
        self.visited: list[str] = []

    def set_default_timeout(self, _timeout: float) -> None:
        pass

    def goto(self, url: str, **_: Any) -> None:
        self.url = url
        self.visited.append(url)

    def wait_for_timeout(self, _timeout: int) -> None:
        pass

    def evaluate(self, _script: str) -> str | None:
        return self.token


class FakeContext:
    pages: list[FakePage]

    def __init__(self, page: FakePage) -> None:
        self.pages = [page]
        self.closed = False

    def cookies(self) -> list[dict[str, str]]:
        return [{"name": "session", "value": "private-cookie", "domain": ".wildberries.ru"}]

    def close(self) -> None:
        self.closed = True


def configured(tmp_path: Path, token: str | None = None) -> tuple[WildberriesSession, FakePage, FakeContext]:
    client = WildberriesSession(settings=WildberriesSettings(profile_dir=tmp_path / "wb-profile"))
    page = FakePage(token)
    context = FakeContext(page)
    client._page = page
    client._context = context
    client._playwright = Mock()
    return client, page, context


def test_open_login_leaves_persistent_browser_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, page, context = configured(tmp_path)
    monkeypatch.setattr(client, "_ensure_browser", lambda: None)

    status = client.open_login()

    assert status.signed_in is False
    assert status.browser_open is True
    assert page.visited == ["https://www.wildberries.ru/lk/mypurchases"]
    assert context.closed is False


def test_missing_token_keeps_interactive_login_window_open(tmp_path: Path) -> None:
    client, _, context = configured(tmp_path)

    with pytest.raises(WildberriesSignedOutError, match="open_login"):
        client._read_from_browser()

    assert context.closed is False
    assert client._page is not None


def test_status_does_not_launch_an_empty_profile(tmp_path: Path) -> None:
    client = WildberriesSession(settings=WildberriesSettings(profile_dir=tmp_path / "missing"))

    status = client.status()

    assert status.signed_in is False
    assert status.browser_open is False
    assert client._page is None


def test_token_and_cookies_are_kept_in_memory_then_browser_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, context = configured(tmp_path, "opaque.token.value")
    monkeypatch.setattr(client, "expiry_of", lambda _token: 10**12)

    assert client.token() == "opaque.token.value"
    assert client._cookies == {"session": "private-cookie"}
    assert context.closed is True
    assert client._page is None


def test_rejected_session_has_safe_reauthentication_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = WildberriesSession(settings=WildberriesSettings(profile_dir=tmp_path / "wb-profile"))
    first = SimpleNamespace(status_code=401)
    second = SimpleNamespace(status_code=401)
    send = Mock(side_effect=[first, second])
    monkeypatch.setattr(client, "_send", send)

    with pytest.raises(WildberriesSignedOutError) as error:
        client._call("POST", "https://www.wildberries.ru/private", json={})

    assert error.value.code is ErrorCode.SESSION_EXPIRED
    assert "wildberries_open_login" in str(error.value)
    assert "private-cookie" not in str(error.value)
    assert send.call_count == 2
