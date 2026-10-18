from pathlib import Path
from unittest.mock import Mock

import pytest

from marketplace_mcp.adapters.yandex_market.services import cart, favorites
from marketplace_mcp.adapters.yandex_market.session import (
    YandexMarketError,
    YandexMarketSession,
    YandexMarketSettings,
)


def test_yandex_writes_are_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    session = YandexMarketSession(YandexMarketSettings(profile_dir=Path("unused")))
    monkeypatch.setattr(cart, "get_session", lambda: session)
    monkeypatch.setattr(favorites, "get_session", lambda: session)

    with pytest.raises(YandexMarketError, match="writes_disabled"):
        cart.add_to_cart("123456")
    with pytest.raises(YandexMarketError, match="writes_disabled"):
        favorites.set_favorite("123456")


def test_favorite_change_returns_confirmed_result(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock()
    session.settings.enable_writes = True
    session.set_product_favorite.return_value = True
    monkeypatch.setattr(favorites, "get_session", lambda: session)
    monkeypatch.setattr(favorites, "_product_path", lambda _: ("/card/chay/123456", "123456"))

    result = favorites.set_favorite("123456", add=True)

    assert result.ok is True
    session.set_product_favorite.assert_called_once_with("/card/chay/123456", add=True)


def test_cart_addition_returns_read_back_result(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock()
    session.settings.enable_writes = True
    session.add_product_to_cart.return_value = True
    monkeypatch.setattr(cart, "get_session", lambda: session)
    product = Mock(url="https://market.yandex.ru/card/chay/123456", title="Чай")
    monkeypatch.setattr(cart, "product_details", lambda _: product)
    monkeypatch.setattr(cart, "_product_path", lambda _: ("/card/chay/123456", "123456"))

    result = cart.add_to_cart("123456")

    assert result.ok is True
    session.add_product_to_cart.assert_called_once_with("/card/chay/123456", "123456", "Чай")


def test_unconfirmed_write_is_not_reported_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock()
    session.settings.enable_writes = True
    session.set_product_favorite.return_value = False
    monkeypatch.setattr(favorites, "get_session", lambda: session)
    monkeypatch.setattr(favorites, "_product_path", lambda _: ("/card/chay/123456", "123456"))

    result = favorites.set_favorite("123456")

    assert result.ok is False
    assert result.detail
