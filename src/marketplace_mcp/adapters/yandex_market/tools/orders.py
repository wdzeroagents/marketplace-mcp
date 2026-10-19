"""Order listing and shared-store synchronization tools."""

from typing import Annotated, Any, Literal

from pydantic import Field

from marketplace_mcp.adapters.yandex_market.models.orders import YandexMarketOrderGroup
from marketplace_mcp.adapters.yandex_market.services import orders
from marketplace_mcp.adapters.yandex_market.session import get_session
from marketplace_mcp.adapters.yandex_market.source import YandexMarketSource
from marketplace_mcp.core.dependencies import run_blocking
from marketplace_mcp.core.store.runtime import run_with_store
from marketplace_mcp.core.store.sync import sync_orders as _sync_orders
from marketplace_mcp.core.utils.annotations import Limit
from marketplace_mcp.mcp_server import mcp


@mcp.tool()
async def yandex_market_list_orders(
    scope: Annotated[
        Literal["active", "completed"], Field(description="Active deliveries or completed history.")
    ] = "active",
    limit: Limit = 100,
) -> list[YandexMarketOrderGroup]:
    """Read Yandex Market order groups and their current Russian status via JSON API.

    Requires a signed-in Yandex Market browser profile. Complete login with
    yandex_market_open_login() and verify with yandex_market_session_status().
    Limit counts groups, which can contain several order numbers. Completed does
    not imply received: use the status text. Detail links are navigation links.
    Read-only; does not require Ozon login.
    """
    return await run_blocking(lambda: orders.list_orders(scope, limit))


@mcp.tool()
async def yandex_market_sync_orders(
    full: Annotated[bool, Field(description="Re-read all orders, including settled ones.")] = False,
    limit: Annotated[int, Field(ge=1, le=1000, description="Maximum number of newest orders to inspect.")] = 1000,
) -> dict[str, Any]:
    """Synchronize buyer orders and available item details to the shared store.

    Read it with marketplace_orders(marketplace="yandex_market") and
    marketplace_order_details(marketplace="yandex_market", order_number=...).
    Items use a synthetic parcel key when no parcel id is exposed; recipient and
    delivery address are not copied into the store.
    """
    source = YandexMarketSource(get_session())
    report = await run_blocking(
        lambda: run_with_store(lambda connection: _sync_orders(connection, source, full=full, limit=limit))
    )
    return report.__dict__
