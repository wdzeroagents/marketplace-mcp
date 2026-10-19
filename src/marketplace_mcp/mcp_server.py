"""The MCP server itself: the instance every tool registers on.

Kept apart from the tools so that a tool module can import the server without
the server having to know about the tools — the tools are attached in
``main``, which is the only place that knows the whole set.

``instructions`` is what a client is handed on connect, and it is the only
documentation an agent gets before it starts calling things.
"""

from typing import Final

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from marketplace_mcp.settings import get_server_settings

INSTRUCTIONS: Final = """Overview
This server has independent buyer adapters for Ozon, Wildberries, and Yandex Market. Signing in to
one marketplace does not sign in to another. Ozon has account, catalog, checkout, and finance tools;
Wildberries syncs buyer orders and prices; Yandex Market has catalog tools, gated cart/favorites,
and buyer orders. Browser profiles and permissions are separate.

Shared store
Sync before reading when the local copy may be empty or stale: Ozon uses sync_orders(), Wildberries
uses wildberries_sync_orders(), and Yandex Market uses yandex_market_sync_orders(). Read normalized
orders with marketplace_orders(marketplace=...) and details with
marketplace_order_details(marketplace=..., order_number=...). Status text stays in the marketplace's
own wording. Ozon and Wildberries expose parcel details; Yandex Market provides order-level items
only, stored under one synthetic parcel key, yandex-order:{order_number}. Its store omits payment
method, parcel splits, recipient, and delivery address.

Errors
Failures carry a leading code such as [upstream_unavailable], [rate_limited], [session_expired],
[writes_disabled], [orders_disabled], or [total_mismatch]. Branch on the code and relay the message:
an error is not an empty account. Recover a signed-out session in that marketplace's login flow.

Wildberries
Call wildberries_open_login(), sign in in its browser, and verify with wildberries_session_status().
Call wildberries_sync_orders() before reading the shared store. wildberries_sync_prices() records
historical purchase prices, not current catalog prices. Token and cookies stay out of MCP arguments.

Yandex Market
Call yandex_market_open_login(), finish sign-in or any challenge, then verify with
yandex_market_session_status(). Search public products with yandex_market_search() and
yandex_market_product_details(). yandex_market_list_orders() reads without saving; use
yandex_market_sync_orders() to update the shared store. completed does not mean received; use the
original status text. Cart and favorite changes are disabled unless
YANDEX_MARKET_ENABLE_WRITES=1. Cookies and request headers stay in its browser profile.

Ozon
All Ozon tools act on the signed-in buyer account; money is real. Start with session_status(): it
reports the session, writes_enabled, and orders_enabled gates. The operator controls both gates.

For a purchase, follow this order: search() -> product_details() for the exact SKU (including the
size-specific SKU for apparel); set_cart_quantity(); select_cart_items(..., mode="only"); read
get_checkout() for payment methods, pickup points, pay-on-delivery, and totals; configure_checkout()
from that result; show totals.order_total; then place_order(confirm_total=<shown total>). Use
pay_order() only when payment remains pending. cancel_order() cancels an order; optional skus target
individual lines. Selected cart ticks define the order contents, and get_checkout() is empty until
something is selected.

Wishlists (get_lists / create_list / set_list_membership) differ from curated selections
(list_selections / selection_products / create_selection / add_to_selection / remove_from_selection).
Selections are UUID-addressed, publishable, and contain only favorites; read their products
separately. Publishing appears on the owner's public profile, so ask first.

Never confuse totals.total (charged now) with totals.order_total (full order cost). Pay-on-delivery
can make today's charge 0 RUB while the order still costs money. pay_after_receipt.scope is full,
partial (with pay_now_items and pay_on_receipt_items), or none. list_orders() has no order total;
use amount_due_at_pickup for collection and each item's price/paid flag only for that item. paid=null
means unknown. active omits received and cancelled rows; state explains the outcome.

Product cards show price (the account's bank price), price_regular (other banks), and price_old;
only price is charged. Use it for ranking. Search limit is depth, not page size, and the cheapest lot
may be later. Search is literal: search the model without the brand if a listing omits it, then
verify with product_details() because seller titles may name no model. No exact result means no
result, even if Ozon shows recommendations. find_cheaper() adds Ozon's own cheaper-or-faster offers.

product_details() returns Ozon's rating, reviews_count, and questions_count; get_reviews() returns a
star breakdown plus up to limit reviews. count is the product total; fetched is what came back.
There is no star filter: use sort="worst" and depth. Reviews keep pros and cons separate and name
their size/color variant. list_orders() dates are status dates; archive ranges are walked down to,
so cost follows depth rather than range width.

Purchases list what was ordered, including refused items, without status and at today's catalog
price. Use bought_items() to check what was received: parcel outcomes can differ within one order.
The scan reports scanned_orders, scanned_back_to, complete, unresolved, and provisional. Continue
with bought_items(skus=<unresolved + provisional>, scan_before=<scanned_back_to>) until complete,
merge by SKU preferring received, and never call unresolved "not bought": the scan has not reached
it. A first query takes about 40-50 s; each 150-order continuation about 30 s.

Ozon failures never masquerade as an empty result. Recover a signed-out session with
start_login(login) and submit_login_code(code); ask the account owner for the one-time code. Card
payment finishes on the bank's domain; this server holds no bank credentials. pay_order() reports
the amount, any top-up needed, and the page to finish on; pay-on-delivery avoids bank sign-in.
Prices, dates, and addresses use Ozon's original wording and RUB. Pass identifiers back unchanged."""


def _transport_security() -> TransportSecuritySettings:
    """Whether to check the Host header, and against what.

    The check is an exact match, so it can only be enabled by naming the hosts:
    with none named it stays off, or every client using the address it was given
    would be answered 421 by a server that is working correctly.
    """
    allowed = get_server_settings().allowed_hosts
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(allowed),
        allowed_hosts=allowed,
    )


mcp: Final = FastMCP("marketplace", instructions=INSTRUCTIONS, transport_security=_transport_security())
