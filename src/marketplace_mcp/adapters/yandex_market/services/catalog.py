"""Read public search results and product details from rendered Market pages."""

import re
from urllib.parse import urlsplit

from pydantic import ValidationError

from marketplace_mcp.adapters.yandex_market.models.catalog import YandexMarketProduct, YandexMarketTile
from marketplace_mcp.adapters.yandex_market.session import YandexMarketError, get_session
from marketplace_mcp.core.errors import ErrorCode

_PRODUCT_PATH = re.compile(r"^/card/[^/?#]+/(\d+)/?$")


def _product_path(product_id_or_url: str) -> tuple[str, str]:
    value = product_id_or_url.strip()
    if value.isascii() and value.isdigit():
        product_id = value
        matches = [item for item in get_session().search_page(value, 16) if item.get("product_id") == product_id]
        found_url = matches[0].get("url") if matches else None
        if not isinstance(found_url, str):
            raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market did not find that product ID.")
        path = urlsplit(found_url).path
    else:
        parsed = urlsplit(value if "://" in value else "https://market.yandex.ru" + value)
        if parsed.hostname != "market.yandex.ru":
            raise ValueError("Use a Yandex Market product-card URL or numeric product ID")
        path = parsed.path
        product_id = ""
    match = _PRODUCT_PATH.fullmatch(path)
    if not match:
        raise ValueError("Use a Yandex Market product-card URL or numeric product ID")
    resolved_id = product_id or match.group(1)
    if not isinstance(resolved_id, str):
        raise TypeError("The product-card path did not contain a string ID")
    return path.rstrip("/"), resolved_id


def search(query: str, limit: int = 16) -> list[YandexMarketTile]:
    rows = get_session().search_page(query, limit)
    result: list[YandexMarketTile] = []
    for row in rows:
        price = row.get("price")
        if isinstance(price, str) and price and "₽" not in price:
            row["price"] = f"{price} ₽"
        row["reviews_count_display"] = row.pop("reviews_count", None)
        try:
            result.append(YandexMarketTile.model_validate(row))
        except ValidationError as exc:
            raise YandexMarketError(
                ErrorCode.UPSTREAM, "Yandex Market search results are incomplete or have changed."
            ) from exc
    return result


def product_details(product_id_or_url: str) -> YandexMarketProduct:
    path, product_id = _product_path(product_id_or_url)
    row = get_session().product_page(path)
    row["product_id"] = row.get("product_id") or product_id
    price = row.get("price")
    if price is not None and row.get("currency") == "RUB":
        row["price"] = f"{price} ₽"
    try:
        return YandexMarketProduct.model_validate(row)
    except ValidationError as exc:
        raise YandexMarketError(
            ErrorCode.UPSTREAM, "Yandex Market product details are incomplete or have changed."
        ) from exc
