"""Namespaced, read-only buyer tools; no dependency on an Ozon login."""

from typing import Annotated, Literal

from pydantic import Field

from marketplace_mcp.adapters.yandex_market import orders
from marketplace_mcp.core.dependencies import run_blocking
from marketplace_mcp.core.utils.annotations import Limit
from marketplace_mcp.mcp_server import mcp


@mcp.tool()
async def yandex_market_list_orders(
    scope: Annotated[
        Literal["active", "completed"], Field(description="Active deliveries or completed order history.")
    ] = "active",
    limit: Limit = 100,
) -> list[orders.YandexMarketOrderGroup]:
    """Read Yandex Market order groups and their current Russian status via JSON API.

    Requires operator-configured YANDEX_MARKET_SESSION_ID and YANDEX_MARKET_SK;
    never pass credentials as tool arguments. Limit counts delivery groups, which
    can contain several order numbers. Completed does not imply received: use
    the status text. Detail links are navigation links, not fetched order details.
    No payment, products, ETA or automatic session renewal is inferred. Errors
    raise rather than return an empty account. Read-only; does not require Ozon login.
    """
    return await run_blocking(lambda: orders.list_orders(scope, limit))
