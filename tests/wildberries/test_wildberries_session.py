from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from marketplace_mcp.adapters.wildberries.constants import ARCHIVE, PURCHASES_PAGE, TOKEN_STORAGE_KEY
from marketplace_mcp.adapters.wildberries.session import (
    WildberriesSession,
    WildberriesSettings,
    WildberriesSignedOutError,
    WildberriesUpstreamError,
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


def test_token_is_kept_in_memory_then_temporary_browser_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, context = configured(tmp_path, "opaque.token.value")
    monkeypatch.setattr(client, "expiry_of", lambda _token: 10**12)

    assert client.token() == "opaque.token.value"
    assert context.closed is True
    assert client._page is None


def test_account_request_runs_inside_browser_with_implicit_cookies(tmp_path: Path) -> None:
    client, page, _ = configured(tmp_path, "private-token")
    page.evaluate = Mock(return_value={"status": 200, "body": '{"value":{"archive":[]}}'})

    response = client._send("POST", ARCHIVE, json={})

    assert response.status_code == 200
    assert response.json() == {"value": {"archive": []}}
    script, payload = page.evaluate.call_args.args
    assert "localStorage.getItem(tokenKey)" in script
    assert 'localStorage.getItem("wbx__sessionID")' in script
    assert 'part.startsWith("_wbauid=")' in script
    assert 'credentials: "include"' in script
    assert payload["tokenKey"] == TOKEN_STORAGE_KEY
    assert "private-token" not in str(payload)
    assert page.visited == [PURCHASES_PAGE]


def test_account_request_rejects_non_wildberries_origin(tmp_path: Path) -> None:
    client = WildberriesSession(settings=WildberriesSettings(profile_dir=tmp_path / "wb-profile"))

    with pytest.raises(ValueError, match="Wildberries origin"):
        client._send("GET", "https://attacker.example/orders")


def test_antibot_block_is_not_misreported_as_expired_login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = WildberriesSession(settings=WildberriesSettings(profile_dir=tmp_path / "wb-profile"))
    send = Mock(return_value=SimpleNamespace(status_code=498))
    monkeypatch.setattr(client, "_send", send)

    with pytest.raises(WildberriesUpstreamError, match="anti-bot"):
        client._call("POST", ARCHIVE, json={})

    assert send.call_count == 1


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
