"""Explicitly gated favorite changes through the first-party product card."""

from marketplace_mcp.adapters.yandex_market.models.common import YandexMarketWriteResult
from marketplace_mcp.adapters.yandex_market.services.catalog import _product_path
from marketplace_mcp.adapters.yandex_market.session import YandexMarketError, get_session
from marketplace_mcp.core.errors import ErrorCode


def set_favorite(product_id_or_url: str, *, add: bool = True) -> YandexMarketWriteResult:
    session = get_session()
    if not session.settings.enable_writes:
        raise YandexMarketError(
            ErrorCode.WRITES_DISABLED,
            "Yandex Market account changes are disabled. Set YANDEX_MARKET_ENABLE_WRITES=1 "
            "to allow cart and favorite changes.",
        )
    path, _ = _product_path(product_id_or_url)
    if session.set_product_favorite(path, add=add):
        return YandexMarketWriteResult()
    return YandexMarketWriteResult(
        ok=False,
        detail="The favorite state did not match the requested change; check the product card in the browser.",
    )
