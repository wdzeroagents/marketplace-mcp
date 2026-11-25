"""The stable vocabulary for marketplace features exposed through MCP.

Adapters deliberately keep their own tools and response models: a product ID,
cart offer, or checkout is meaningful only on the marketplace that issued it.
This module supplies the small cross-adapter contract needed before choosing a
tool.  It makes a missing feature explicit rather than asking clients to infer
support from an absent or differently named tool.
"""

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, Field

from marketplace_mcp.core.store.read import MarketplaceName


class CapabilityName(StrEnum):
    """Operations that a buyer marketplace may expose."""

    SESSION_LOGIN = "session_login"
    SESSION_STATUS = "session_status"
    PRODUCT_SEARCH = "product_search"
    PRODUCT_DETAILS = "product_details"
    CART_READ = "cart_read"
    CART_WRITE = "cart_write"
    FAVORITES_READ = "favorites_read"
    FAVORITES_WRITE = "favorites_write"
    ORDERS_LIVE = "orders_live"
    ORDERS_SYNC = "orders_sync"
    ORDERS_READ = "orders_read"
    ORDER_DETAILS = "order_details"
    PRICE_HISTORY_SYNC = "price_history_sync"


class CapabilityState(StrEnum):
    """Whether an operation is usable in the installed adapter."""

    AVAILABLE = "available"
    GATED = "gated"
    UNAVAILABLE = "unavailable"


class Capability(BaseModel):
    """One operation, its state, and the MCP tools that implement it."""

    name: CapabilityName = Field(description="Stable cross-marketplace operation name.")
    state: CapabilityState = Field(description="available, gated by a setting, or unavailable in this adapter.")
    tools: tuple[str, ...] = Field(description="Existing MCP tools to call when this operation is available.")
    detail: str = Field(description="Constraint or usage note for this marketplace.")


class MarketplaceCapabilities(BaseModel):
    """The capability manifest for one buyer adapter."""

    marketplace: MarketplaceName = Field(description="Marketplace identifier used by shared-store tools.")
    capabilities: tuple[Capability, ...] = Field(description="Every operation in the stable capability vocabulary.")


def _capability(
    name: CapabilityName,
    state: CapabilityState,
    tools: tuple[str, ...] = (),
    detail: str = "",
) -> Capability:
    return Capability(name=name, state=state, tools=tools, detail=detail)


CAPABILITIES: Final[dict[MarketplaceName, MarketplaceCapabilities]] = {
    "ozon": MarketplaceCapabilities(
        marketplace="ozon",
        capabilities=(
            _capability(CapabilityName.SESSION_LOGIN, CapabilityState.AVAILABLE, ("start_login", "submit_login_code")),
            _capability(CapabilityName.SESSION_STATUS, CapabilityState.AVAILABLE, ("session_status",)),
            _capability(CapabilityName.PRODUCT_SEARCH, CapabilityState.AVAILABLE, ("search", "get_search_filters")),
            _capability(CapabilityName.PRODUCT_DETAILS, CapabilityState.AVAILABLE, ("product_details",)),
            _capability(CapabilityName.CART_READ, CapabilityState.AVAILABLE, ("get_cart",)),
            _capability(
                CapabilityName.CART_WRITE,
                CapabilityState.GATED,
                ("set_cart_quantity", "select_cart_items"),
                "Enable OZON_ENABLE_WRITES before changing the cart.",
            ),
            _capability(CapabilityName.FAVORITES_READ, CapabilityState.AVAILABLE, ("list_favorites", "get_lists")),
            _capability(
                CapabilityName.FAVORITES_WRITE,
                CapabilityState.GATED,
                ("set_favorite", "set_list_membership"),
                "Enable OZON_ENABLE_WRITES before changing favorites or lists.",
            ),
            _capability(CapabilityName.ORDERS_LIVE, CapabilityState.AVAILABLE, ("list_orders",)),
            _capability(CapabilityName.ORDERS_SYNC, CapabilityState.AVAILABLE, ("sync_orders",)),
            _capability(CapabilityName.ORDERS_READ, CapabilityState.AVAILABLE, ("marketplace_orders",)),
            _capability(CapabilityName.ORDER_DETAILS, CapabilityState.AVAILABLE, ("marketplace_order_details",)),
            _capability(CapabilityName.PRICE_HISTORY_SYNC, CapabilityState.AVAILABLE, ("sync_prices",)),
        ),
    ),
    "wildberries": MarketplaceCapabilities(
        marketplace="wildberries",
        capabilities=(
            _capability(CapabilityName.SESSION_LOGIN, CapabilityState.AVAILABLE, ("wildberries_open_login",)),
            _capability(CapabilityName.SESSION_STATUS, CapabilityState.AVAILABLE, ("wildberries_session_status",)),
            _capability(
                CapabilityName.PRODUCT_SEARCH,
                CapabilityState.UNAVAILABLE,
                detail="The adapter has no buyer-side catalog endpoint yet.",
            ),
            _capability(
                CapabilityName.PRODUCT_DETAILS,
                CapabilityState.UNAVAILABLE,
                detail="The adapter returns product data only from synchronized orders.",
            ),
            _capability(
                CapabilityName.CART_READ, CapabilityState.UNAVAILABLE, detail="Cart access is not implemented."
            ),
            _capability(
                CapabilityName.CART_WRITE, CapabilityState.UNAVAILABLE, detail="Cart access is not implemented."
            ),
            _capability(
                CapabilityName.FAVORITES_READ,
                CapabilityState.UNAVAILABLE,
                detail="Favorites access is not implemented.",
            ),
            _capability(
                CapabilityName.FAVORITES_WRITE,
                CapabilityState.UNAVAILABLE,
                detail="Favorites access is not implemented.",
            ),
            _capability(
                CapabilityName.ORDERS_LIVE,
                CapabilityState.AVAILABLE,
                ("wildberries_sync_orders",),
                "The active-order endpoint is synchronized directly into the shared store.",
            ),
            _capability(CapabilityName.ORDERS_SYNC, CapabilityState.AVAILABLE, ("wildberries_sync_orders",)),
            _capability(CapabilityName.ORDERS_READ, CapabilityState.AVAILABLE, ("marketplace_orders",)),
            _capability(CapabilityName.ORDER_DETAILS, CapabilityState.AVAILABLE, ("marketplace_order_details",)),
            _capability(CapabilityName.PRICE_HISTORY_SYNC, CapabilityState.AVAILABLE, ("wildberries_sync_prices",)),
        ),
    ),
    "yandex_market": MarketplaceCapabilities(
        marketplace="yandex_market",
        capabilities=(
            _capability(CapabilityName.SESSION_LOGIN, CapabilityState.AVAILABLE, ("yandex_market_open_login",)),
            _capability(CapabilityName.SESSION_STATUS, CapabilityState.AVAILABLE, ("yandex_market_session_status",)),
            _capability(CapabilityName.PRODUCT_SEARCH, CapabilityState.AVAILABLE, ("yandex_market_search",)),
            _capability(CapabilityName.PRODUCT_DETAILS, CapabilityState.AVAILABLE, ("yandex_market_product_details",)),
            _capability(
                CapabilityName.CART_READ, CapabilityState.UNAVAILABLE, detail="Cart listing is not implemented."
            ),
            _capability(
                CapabilityName.CART_WRITE,
                CapabilityState.GATED,
                ("yandex_market_add_to_cart",),
                "Enable YANDEX_MARKET_ENABLE_WRITES; adding uses the card's primary offer once.",
            ),
            _capability(
                CapabilityName.FAVORITES_READ,
                CapabilityState.UNAVAILABLE,
                detail="Favorites listing is not implemented.",
            ),
            _capability(
                CapabilityName.FAVORITES_WRITE,
                CapabilityState.GATED,
                ("yandex_market_set_favorite",),
                "Enable YANDEX_MARKET_ENABLE_WRITES before changing favorites.",
            ),
            _capability(CapabilityName.ORDERS_LIVE, CapabilityState.AVAILABLE, ("yandex_market_list_orders",)),
            _capability(CapabilityName.ORDERS_SYNC, CapabilityState.AVAILABLE, ("yandex_market_sync_orders",)),
            _capability(CapabilityName.ORDERS_READ, CapabilityState.AVAILABLE, ("marketplace_orders",)),
            _capability(CapabilityName.ORDER_DETAILS, CapabilityState.AVAILABLE, ("marketplace_order_details",)),
            _capability(
                CapabilityName.PRICE_HISTORY_SYNC,
                CapabilityState.UNAVAILABLE,
                detail="Purchase-price synchronization is not implemented.",
            ),
        ),
    ),
}


def capabilities_for(marketplace: MarketplaceName | None = None) -> tuple[MarketplaceCapabilities, ...]:
    """Return one manifest, or every manifest in stable marketplace order."""
    if marketplace is not None:
        return (CAPABILITIES[marketplace],)
    return tuple(CAPABILITIES[name] for name in ("ozon", "wildberries", "yandex_market"))
