"""Session management tools for Yandex Market."""

from marketplace_mcp.adapters.yandex_market import session as browser_session
from marketplace_mcp.core.dependencies import run_blocking
from marketplace_mcp.mcp_server import mcp


@mcp.tool()
async def yandex_market_open_login() -> browser_session.YandexMarketSessionStatus:
    """Open Yandex Market in the adapter's persistent browser profile.

    Sign in and complete any access challenge directly in that browser. No
    cookies, session headers, or login codes are passed through MCP arguments.
    Check yandex_market_session_status() after signing in.
    """
    return await run_blocking(browser_session.get_session().open_login)


@mcp.tool()
async def yandex_market_session_status() -> browser_session.YandexMarketSessionStatus:
    """Verify that the persistent Yandex Market browser session can read orders."""
    return await run_blocking(browser_session.get_session().status)
