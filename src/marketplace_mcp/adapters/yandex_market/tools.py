"""Namespaced buyer tools; no dependency on an Ozon login."""

from typing import Annotated, Any, Literal

from pydantic import Field

# Importing these modules registers their tools on the shared FastMCP instance.
from marketplace_mcp.adapters.yandex_market import (
    orders,
    session,
    tools_cart as _cart_tools,
    tools_catalog as _catalog_tools,
    tools_favorites as _favorites_tools,
)
from marketplace_mcp.adapters.yandex_market.source import YandexMarketSource
from marketplace_mcp.core.dependencies import run_blocking
from marketplace_mcp.core.store import connect
from marketplace_mcp.core.store.sync import sync_orders as _sync_orders
from marketplace_mcp.settings import get_settings
from marketplace_mcp.core.utils.annotations import Limit
from marketplace_mcp.mcp_server import mcp

_REGISTERED_TOOL_MODULES = (_cart_tools, _catalog_tools, _favorites_tools)


@mcp.tool()
async def yandex_market_open_login() -> session.YandexMarketSessionStatus:
    """Open Yandex Market in the adapter's persistent browser profile.

    Sign in and complete any access challenge directly in that browser. No
    cookies, session headers, or login codes are passed through MCP arguments.
    Check yandex_market_session_status() after signing in.
    """
    return await run_blocking(session.get_session().open_login)


@mcp.tool()
async def yandex_market_session_status() -> session.YandexMarketSessionStatus:
    """Verify that the persistent Yandex Market browser session can read orders."""
    return await run_blocking(session.get_session().status)


@mcp.tool()
async def yandex_market_list_orders(
    scope: Annotated[
        Literal["active", "completed"], Field(description="Active deliveries or completed order history.")
    ] = "active",
    limit: Limit = 100,
) -> list[orders.YandexMarketOrderGroup]:
    """Read Yandex Market order groups and their current Russian status via JSON API.

    Requires a signed-in Yandex Market browser profile. If signed out, call
    yandex_market_open_login(), sign in directly in the browser, then verify with
    yandex_market_session_status(). Limit counts delivery groups, which can
    contain several order numbers. Completed does not imply received: use the
    status text. Detail links are navigation links, not fetched order details.
    Read-only; does not require Ozon login.
    """
    return await run_blocking(lambda: orders.list_orders(scope, limit))


@mcp.tool()
async def yandex_market_sync_orders(
    full: Annotated[bool, Field(description="Re-read all orders, including settled ones.")] = False,
    limit: Annotated[int, Field(ge=1, le=1000, description="Maximum number of newest orders to inspect.")] = 1000,
) -> dict[str, Any]:
    """Synchronize Yandex Market buyer orders and available item details.

    Sign in with yandex_market_open_login first. Then read the local copy with
    marketplace_orders(marketplace="yandex_market") and
    marketplace_order_details(marketplace="yandex_market", order_number=...).
    Yandex provides order-level items on its detail page; when it does not
    expose a parcel id, the local parcel key is namespaced from the order id.
    Recipient and delivery address are not copied into the store.
    """
    source = YandexMarketSource(session.get_session())

    def sync() -> Any:
        connection = connect(get_settings().store_path)
        try:
            return _sync_orders(connection, source, full=full, limit=limit)
        finally:
            connection.close()

    report = await run_blocking(sync)
    return report.__dict__
