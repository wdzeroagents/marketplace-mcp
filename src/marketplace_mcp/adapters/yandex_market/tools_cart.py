"""Cart tools for the Yandex Market buyer account."""

from typing import Annotated

from pydantic import Field

from marketplace_mcp.adapters.yandex_market.models.common import YandexMarketWriteResult
from marketplace_mcp.adapters.yandex_market.services import cart
from marketplace_mcp.core.dependencies import run_blocking
from marketplace_mcp.mcp_server import mcp


@mcp.tool()
async def yandex_market_add_to_cart(
    product_id_or_url: Annotated[
        str,
        Field(description="Numeric product ID from search, or its full Yandex Market product-card URL."),
    ],
) -> YandexMarketWriteResult:
    """[GATED by YANDEX_MARKET_ENABLE_WRITES] Add the primary offer once; already-present items are not duplicated."""
    return await run_blocking(lambda: cart.add_to_cart(product_id_or_url))
