# Yandex Market buyer tools

The adapter uses its own persistent browser profile. Sign in with
`yandex_market_open_login()` and verify the session with
`yandex_market_session_status()`. Complete any Yandex access challenge manually in
that browser. Cookies and short-lived request values stay in the browser; do not
copy them into MCP arguments or environment variables. The profile defaults to
`/data/yandex-market-profile`; set `YANDEX_MARKET_PROFILE_DIR` to choose another
location. On Windows, `YANDEX_MARKET_BROWSER_CHANNEL` can select an installed
browser such as `msedge` or `chrome`.
The browser context closes lazily after `MARKETPLACE_IDLE_SECONDS` (default
600); the timeout is checked on the next browser operation, which reopens the
saved profile.

## Catalog

`yandex_market_search(query, limit=16)` returns visible search tiles with product
ID, title, displayed price, rating, image and a clean product-card URL. One page
contains at most 16 results. `yandex_market_product_details(product_id_or_url)`
accepts a numeric ID from search or a product-card URL and returns the title,
structured price, availability, rating, review count, description and image.

Search is rendered by the storefront resolver
`resolvePoorRemoteSearchApphost`; product data is read from the card's structured
JSON-LD. The browser follows the same storefront flow as the website, so the
adapter does not need to replay opaque search payloads or parse private page
content.

## Cart and favorites

`yandex_market_add_to_cart(product_id_or_url)` adds the primary offer once. It
checks the cart first to avoid adding a duplicate and confirms the item appears
there afterward. `yandex_market_set_favorite(product_id_or_url, add=true)` adds a
product to favorites; `add=false` removes it. The favorite operation checks the
button state before and after the change.

These account changes are disabled by default. Set
`YANDEX_MARKET_ENABLE_WRITES=1` to enable them. This setting does not allow
checkout or order placement; those operations are not implemented for Yandex
Market.

The observed frontend calls were:

- search: `POST /api/resolve/` with `resolvePoorRemoteSearchApphost`;
- favorites: `POST /api/web/market.front.wishlist.Wishlist/addWishlistItem` and
  `.../deleteWishlistItem`;
- cart: `POST /api/web/market.front.purchaseCore.PurchaseCore/prepareCartModelAddItems`.

These are undocumented buyer-side frontend calls, not a supported public buyer
API. The site may change their request format or require another access challenge.
The adapter uses the first-party browser UI for account changes and never exports
the session cookies, `sk`/`skid` values or request body.

## Orders and limits

`yandex_market_list_orders(scope="active"|"completed", limit=100)` reads order
groups and their Russian status from the internal `resolveConsolidationOrders`
resolver. The limit counts delivery groups, each of which can contain several
order numbers. `yandex_market_sync_orders()` writes individual order numbers,
the original status and the visible product lines into the shared store. Read
the saved orders with `marketplace_orders(marketplace="yandex_market")` and
`marketplace_order_details(marketplace="yandex_market", order_number=...)`.

The list uses `POST /api/resolve/` with
`resolveConsolidationOrders:resolveConsolidationOrders`; the browser supplies
its cookies and the short-lived `sk` request value. Order details load from
`/my/order/{order_number}` as server-rendered HTML. No dedicated JSON or
GraphQL detail endpoint was confirmed. The adapter reads the visible order
status, item titles, product IDs and displayed prices from that page. It does
not copy recipient names or delivery addresses. Yandex does not expose a stable
shipment ID in the observed page, so the shared-store parcel-shaped record uses
the explicit key `yandex-order:{order_number}`; it represents order-level items,
not a verified physical parcel. Payment method, parcel split and delivery
address remain unavailable.

Completed means order history, not necessarily received; the original status
text is preserved, and unknown final-state wording remains re-readable. There
is no automatic polling. Product purchase history, payment and delivery
estimates, reviews, and cart listing are not implemented.

An expired session or CAPTCHA raises `[session_expired]` rather than returning an
empty result. Finish sign-in or the challenge manually in the browser and retry.
HTTP 429 is reported as `[rate_limited]`; unexpected responses raise
`[upstream_unavailable]`. All buyer-side calls are internal storefront behavior
and may change without notice. The official Yandex Market Partner API is for
seller operations and is not a buyer-account API.
