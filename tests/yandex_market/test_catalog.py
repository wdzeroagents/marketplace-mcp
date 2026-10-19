from unittest.mock import Mock

import pytest

from marketplace_mcp.adapters.yandex_market.services import catalog
from marketplace_mcp.adapters.yandex_market.session import YandexMarketError


def test_search_adds_currency_and_preserves_displayed_review_count(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock()
    session.search_page.return_value = [
        {
            "product_id": "123456",
            "title": "Чай",
            "price": "283",
            "url": "https://market.yandex.ru/card/chay/123456",
            "image": "https://example.test/image.jpg",
            "rating": "4.8",
            "reviews_count": "157.7K",
        }
    ]
    monkeypatch.setattr(catalog, "get_session", lambda: session)

    result = catalog.search("чай", 3)

    assert result[0].price == "283 ₽"
    assert result[0].rating == pytest.approx(4.8)
    assert result[0].reviews_count_display == "157.7K"
    session.search_page.assert_called_once_with("чай", 3)


def test_product_details_resolves_numeric_id_and_normalizes_json_ld(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock()
    session.search_page.return_value = [{"product_id": "123456", "url": "https://market.yandex.ru/card/chay/123456"}]
    session.product_page.return_value = {
        "product_id": "123456",
        "title": "Чай",
        "price": "283",
        "currency": "RUB",
        "available": True,
        "rating": 4.8,
        "reviews_count": 12,
        "url": "https://market.yandex.ru/card/chay/123456",
    }
    monkeypatch.setattr(catalog, "get_session", lambda: session)

    result = catalog.product_details("123456")

    assert result.price == "283 ₽"
    assert result.reviews_count == 12
    session.product_page.assert_called_once_with("/card/chay/123456")


@pytest.mark.parametrize("value", ["https://example.test/card/chay/123456"])
def test_product_reference_rejects_untrusted_urls(value: str) -> None:
    with pytest.raises(ValueError, match="Yandex Market product-card URL"):
        catalog._product_path(value)


def test_product_reference_discards_tracking_query() -> None:
    assert catalog._product_path("https://market.yandex.ru/card/chay/123456?cpc=tracking#offer") == (
        "/card/chay/123456",
        "123456",
    )


def test_missing_numeric_id_is_not_reported_as_empty_product(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock()
    session.search_page.return_value = []
    monkeypatch.setattr(catalog, "get_session", lambda: session)

    with pytest.raises(YandexMarketError, match="upstream_unavailable"):
        catalog.product_details("123456")
