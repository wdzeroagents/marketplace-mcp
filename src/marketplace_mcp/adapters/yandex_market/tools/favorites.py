"""Favorite tools for the Yandex Market buyer account."""

from typing import Annotated

from pydantic import Field

from marketplace_mcp.adapters.yandex_market.models.common import YandexMarketWriteResult
from marketplace_mcp.adapters.yandex_market.services import favorites
from marketplace_mcp.core.dependencies import run_blocking
from marketplace_mcp.mcp_server import mcp


@mcp.tool()
async def yandex_market_set_favorite(
    product_id_or_url: Annotated[str, Field(description="Numeric product ID or full Yandex Market card URL.")],
    add: Annotated[bool, Field(description="True adds the item; false removes it.")] = True,
) -> YandexMarketWriteResult:
    """[GATED by YANDEX_MARKET_ENABLE_WRITES] Add or remove a product from favorites."""
    return await run_blocking(lambda: favorites.set_favorite(product_id_or_url, add=add))
