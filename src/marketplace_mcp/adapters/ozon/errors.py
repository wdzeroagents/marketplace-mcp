"""Ozon-specific errors use the shared MarketplaceError contract."""

from marketplace_mcp.core.errors import ErrorCode, MarketplaceError


class OzonError(MarketplaceError):
    """An Ozon refusal that has no more specific shared error code."""

    code = ErrorCode.OZON
