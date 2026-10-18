"""Namespaced, read-only buyer tools; no dependency on an Ozon login."""

from typing import Annotated, Literal

from pydantic import Field

from marketplace_mcp.adapters.yandex_market import orders, session
from marketplace_mcp.core.dependencies import run_blocking
from marketplace_mcp.core.utils.annotations import Limit
from marketplace_mcp.mcp_server import mcp


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
