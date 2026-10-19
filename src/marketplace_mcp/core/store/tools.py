"""MCP reads shared by every marketplace that syncs to the local store."""

from typing import Annotated

from pydantic import Field

from marketplace_mcp.core.dependencies import run_blocking
from marketplace_mcp.core.store import read
from marketplace_mcp.core.store.runtime import run_with_store as _run
from marketplace_mcp.mcp_server import mcp


@mcp.tool()
async def marketplace_orders(
    marketplace: Annotated[
        read.MarketplaceName,
        Field(description="Which marketplace's synchronized orders to read."),
    ],
    scope: Annotated[
        read.OrderScope,
        Field(description="all orders, only active orders, or completed orders."),
    ] = "all",
    limit: Annotated[int, Field(ge=1, le=1000, description="Maximum number of orders to return.")] = 100,
) -> list[dict[str, object]]:
    """Read normalized orders from the shared local store.

    Call the marketplace's sync tool first when the store is empty or stale.
    Status is preserved in the marketplace's original wording alongside the
    common active/received/cancelled state.
    """
    return await run_blocking(lambda: _run(lambda store: read.list_orders(store, marketplace, scope, limit)))


@mcp.tool()
async def marketplace_order_details(
    marketplace: Annotated[
        read.MarketplaceName,
        Field(description="Which marketplace's synchronized order to read."),
    ],
    order_number: Annotated[
        str,
        Field(min_length=1, max_length=100, description="Order number from marketplace_orders."),
    ],
) -> dict[str, object] | None:
    """Read one stored order with its parcels, delivery details, and items.

    Returns null when the order has not been synchronized or the number is not
    present in that marketplace's account.
    """
    return await run_blocking(lambda: _run(lambda store: read.order_details(store, marketplace, order_number)))
