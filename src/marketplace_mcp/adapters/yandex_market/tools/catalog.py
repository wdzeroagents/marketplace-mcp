"""Product search and product-card MCP tools."""

from typing import Annotated

from pydantic import Field

from marketplace_mcp.adapters.yandex_market.models.catalog import YandexMarketProduct, YandexMarketTile
from marketplace_mcp.adapters.yandex_market.services import catalog
from marketplace_mcp.core.dependencies import run_blocking
from marketplace_mcp.mcp_server import mcp


@mcp.tool()
async def yandex_market_search(
    query: Annotated[str, Field(min_length=1, max_length=200, description="Search phrase or product name.")],
    limit: Annotated[int, Field(ge=1, le=16, description="Maximum visible results from one search page.")] = 16,
) -> list[YandexMarketTile]:
    """Search the public catalog and return product IDs, titles, prices and links."""
    return await run_blocking(lambda: catalog.search(query, limit))


@mcp.tool()
async def yandex_market_product_details(
    product_id_or_url: Annotated[str, Field(description="Numeric product ID or full Yandex Market card URL.")],
) -> YandexMarketProduct:
    """Read a product card's title, price, availability, rating, reviews and image."""
    return await run_blocking(lambda: catalog.product_details(product_id_or_url))
