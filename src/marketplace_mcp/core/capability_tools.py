"""MCP discovery tool for the cross-marketplace capability contract."""

from typing import Annotated

from pydantic import Field

from marketplace_mcp.core.capabilities import MarketplaceCapabilities, capabilities_for
from marketplace_mcp.core.store.read import MarketplaceName
from marketplace_mcp.mcp_server import mcp


@mcp.tool()
def marketplace_capabilities(
    marketplace: Annotated[
        MarketplaceName | None,
        Field(description="Optional marketplace to inspect; omit it to compare every adapter."),
    ] = None,
) -> tuple[MarketplaceCapabilities, ...]:
    """Describe the stable capability contract for one or all marketplaces.

    Inspect this before choosing adapter-specific tools. An unavailable
    operation has no safe tool in that adapter; a gated one is implemented but
    requires the setting named in `detail`. The `tools` list contains the exact
    current MCP tool names, while `name` remains stable as adapters evolve.
    """
    return capabilities_for(marketplace)

