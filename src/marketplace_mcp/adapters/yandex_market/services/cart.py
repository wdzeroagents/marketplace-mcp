"""Explicitly gated, idempotent addition to the signed-in buyer's cart."""

from marketplace_mcp.adapters.yandex_market.models.common import YandexMarketWriteResult
from marketplace_mcp.adapters.yandex_market.services.catalog import _product_path, product_details
from marketplace_mcp.adapters.yandex_market.session import YandexMarketError, get_session
from marketplace_mcp.core.errors import ErrorCode


def add_to_cart(product_id_or_url: str) -> YandexMarketWriteResult:
    session = get_session()
    if not session.settings.enable_writes:
        raise YandexMarketError(
            ErrorCode.WRITES_DISABLED,
            "Yandex Market account changes are disabled. Set YANDEX_MARKET_ENABLE_WRITES=1 "
            "to allow cart and favorite changes.",
        )
    product = product_details(product_id_or_url)
    path, product_id = _product_path(product.url)
    if session.add_product_to_cart(path, product_id, product.title):
        return YandexMarketWriteResult()
    return YandexMarketWriteResult(
        ok=False,
        detail="Yandex Market accepted no confirmed cart change; check availability and the cart in the browser.",
    )
