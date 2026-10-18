"""Wildberries sign-in and shared-store tools."""

from typing import Annotated, Any

from pydantic import Field

from marketplace_mcp.adapters.wildberries.session import WildberriesSessionStatus, get_session
from marketplace_mcp.adapters.wildberries.source import WildberriesSource
from marketplace_mcp.core.dependencies import run_blocking
from marketplace_mcp.core.store import connect
from marketplace_mcp.core.store.sync import sync_orders as _sync_orders, sync_prices as _sync_prices
from marketplace_mcp.mcp_server import mcp
from marketplace_mcp.settings import get_settings


def _with_store(work: Any) -> Any:
    connection = connect(get_settings().store_path)
    try:
        return work(connection)
    finally:
        connection.close()


@mcp.tool()
async def wildberries_open_login() -> WildberriesSessionStatus:
    """Open the Wildberries adapter's persistent browser profile for sign-in.

    Sign in there, then call wildberries_session_status. The MCP request does
    not receive or return the bearer token or browser cookies.
    """
    return await run_blocking(get_session().open_login)


@mcp.tool()
async def wildberries_session_status() -> WildberriesSessionStatus:
    """Check whether the Wildberries profile contains a usable session token."""
    return await run_blocking(get_session().status)


@mcp.tool()
async def wildberries_sync_orders(
    full: Annotated[bool, Field(description="Re-read all orders, including settled ones.")] = False,
    limit: Annotated[int, Field(ge=1, le=1000, description="Maximum number of newest orders to walk.")] = 1000,
) -> dict[str, Any]:
    """Synchronize Wildberries orders, parcels, addresses, and purchased items.

    Sign in with wildberries_open_login first. Then use the shared
    marketplace_orders(marketplace="wildberries") and
    marketplace_order_details(marketplace="wildberries", order_number=...) tools
    to read the local copy. Settled orders are skipped on routine runs; active
    or unknown statuses are re-read.
    """
    source = WildberriesSource(get_session())
    report = await run_blocking(
        lambda: _with_store(lambda store: _sync_orders(store, source, full=full, limit=limit))
    )
    return report.__dict__


@mcp.tool()
async def wildberries_sync_prices(
    limit: Annotated[int, Field(ge=1, le=1000, description="Maximum purchase-history lines to inspect.")] = 1000,
) -> dict[str, Any]:
    """Record purchased products and their WB-reported purchase prices.

    WB history gives the amount paid, not today's catalogue price. The result
    is therefore a purchase-price series and differs from Ozon's current-price
    observations.
    """
    source = WildberriesSource(get_session())
    report = await run_blocking(lambda: _with_store(lambda store: _sync_prices(store, source, limit)))
    return report.__dict__
