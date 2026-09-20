from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from marketplace_mcp.adapters.yandex_market import session


def configured() -> session.YandexMarketSession:
    return session.YandexMarketSession(
        session.YandexMarketSettings(session_id=SecretStr("test-session"), sk=SecretStr("test-sk"))
    )


def test_request_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    post = Mock(return_value=Mock(status_code=200, json=Mock(return_value={"results": []})))
    monkeypatch.setattr(session.requests, "post", post)
    client = configured()
    client.page("active")
    kwargs = post.call_args.kwargs
    assert post.call_args.args == (session.RESOLVER,)
    assert kwargs["json"] == {"params": [{"filter": "ACTIVE", "size": 20}], "path": "/my/orders"}
    assert kwargs["allow_redirects"] is False
    assert kwargs["cookies"] == {"Session_id": "test-session"}
    client.page("completed", "cursor")
    assert post.call_args.kwargs["json"]["params"][0]["pageToken"] == "cursor"
    assert post.call_args.kwargs["json"]["path"] == "/my/orders?filter=COMPLETED"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "session_expired"),
        (403, "session_expired"),
        (429, "rate_limited"),
        (502, "upstream_unavailable"),
        (302, "upstream_unavailable"),
    ],
)
def test_http_failures_are_coded(monkeypatch: pytest.MonkeyPatch, status: int, code: str) -> None:
    monkeypatch.setattr(session.requests, "post", Mock(return_value=Mock(status_code=status)))
    with pytest.raises(session.YandexMarketError, match=code):
        configured().page("active")


def test_secrets_are_not_in_errors_or_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    client = configured()
    monkeypatch.setattr(
        session.requests, "post", Mock(side_effect=session.requests.RequestsError("test-session test-sk"))
    )
    with pytest.raises(session.YandexMarketError) as error:
        client.page("active")
    for secret in ["test-session", "test-sk"]:
        assert secret not in str(error.value)
        assert secret not in repr(client.settings)


def test_invalid_json_is_not_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session.requests, "post", Mock(return_value=Mock(status_code=200, json=Mock(side_effect=ValueError("secret"))))
    )
    with pytest.raises(session.YandexMarketError, match="invalid JSON"):
        configured().page("active")


def test_missing_credentials_do_not_make_a_request(monkeypatch: pytest.MonkeyPatch) -> None:
    post = Mock()
    monkeypatch.setattr(session.requests, "post", post)
    client = session.YandexMarketSession(session.YandexMarketSettings(session_id=SecretStr(""), sk=SecretStr("")))
    with pytest.raises(session.YandexMarketError, match="session_expired"):
        client.page("active")
    post.assert_not_called()
