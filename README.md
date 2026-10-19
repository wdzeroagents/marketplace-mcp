*English* · [Русский](README.ru.md)

# Marketplace MCP

MCP server for buyer accounts on Ozon, Wildberries, and Yandex Market. Each adapter has a separate browser profile, login, and permissions.

| Adapter | Available tools |
|---|---|
| Ozon | Orders and returns, purchase history, catalog, cart, favorites and lists, checkout, finance |
| Wildberries | Login, order and historical price synchronization |
| Yandex Market | Login, product search and details, order listing and synchronization, gated cart and favorites |
| Shared store | Normalized order lists and order details across adapters |

## Requirements

All adapters use persistent Chromium profiles. Docker runs Chromium under Xvfb; allocate shared memory with --shm-size=1g and mount /data to persistent storage. Keep the volume private because profiles grant access to buyer accounts. Calls from all adapters use one worker thread and run sequentially, so a long Ozon scan or a pending login blocks calls to the other marketplaces.

The Ozon adapter is documented to require a Russian IP. A Russian-IP requirement for Wildberries and Yandex Market has not been verified; network restrictions can depend on the account and location.

## Quick start

For local development, install dependencies and Chromium, then start the server:

    uv sync
    uv run playwright install --with-deps chromium
    uv run python -m marketplace_mcp

For Docker:

    docker build -t marketplace-mcp .
    docker run -i --rm --shm-size=1g -v /opt/marketplace-mcp:/data marketplace-mcp

The default transport is stdio. For a long-running HTTP server set MARKETPLACE_TRANSPORT=http and publish port 8084. The same port serves /mcp and /metrics.

Sign in separately using ozon session tools, wildberries_open_login(), or yandex_market_open_login(). The session-status tool for each adapter confirms access. Credentials and cookies stay inside their own profiles.

## Shared behavior

Sync orders before reading the local copy when it may be empty or stale: Ozon uses sync_orders(), Wildberries uses wildberries_sync_orders(), and Yandex Market uses yandex_market_sync_orders(). Then use marketplace_orders(marketplace=...) and marketplace_order_details(marketplace=..., order_number=...). Marketplace IDs are part of database keys.

An idle browser context is closed lazily after MARKETPLACE_IDLE_SECONDS (default 600 seconds); the timeout is checked when the next browser operation begins. The saved profile remains and is reopened on demand. Zero disables idle closing.

Errors carry a code such as [session_expired], [rate_limited], or [upstream_unavailable]. An error is not an empty account. Account-changing tools are gated by adapter settings. Ozon checkout can spend money and has a separate gate.

## Tools

Ozon: list_orders, order_products, order_parcels, purchases, bought_items, list_returns, search, get_search_filters, product_details, get_reviews, get_description, delivery_estimate, find_cheaper, get_cart, set_cart_quantity, select_cart_items, list_favorites, set_favorite, get_lists, create_list, delete_list, set_list_membership, check_favorite_price_drops, list_selections, get_selection, selection_products, create_selection, add_to_selection, remove_from_selection, set_selection_items, edit_selection, set_selection_public, delete_selection, get_checkout, configure_checkout, place_order, pay_order, list_cancel_reasons, cancel_order, session_status, start_login, submit_login_code, get_finances, get_points, sync_orders, sync_prices, store_stats, link_duplicates.

Wildberries: wildberries_open_login, wildberries_session_status, wildberries_sync_orders, wildberries_sync_prices.

Yandex Market: yandex_market_open_login, yandex_market_session_status, yandex_market_search, yandex_market_product_details, yandex_market_add_to_cart, yandex_market_set_favorite, yandex_market_list_orders, yandex_market_sync_orders.

Shared store: marketplace_orders, marketplace_order_details.

See [Ozon details](docs/ozon.md), [Wildberries details](docs/wildberries.md), [Yandex Market details](docs/yandex-market.md), and [environment settings](env.example). The Yandex order sync stores order-level items under yandex-order:{order_number}; it does not expose parcel splits, payment method, recipient, or delivery address.

## Configuration

Common settings use the MARKETPLACE_ prefix: MARKETPLACE_STORE_PATH, MARKETPLACE_TRANSPORT, MARKETPLACE_HOST, MARKETPLACE_PORT, MARKETPLACE_ALLOWED_HOSTS, and MARKETPLACE_IDLE_SECONDS. Ozon-specific settings retain OZON_; Wildberries and Yandex Market settings use their own prefixes. See env.example for defaults and descriptions. Older OZON_ aliases for common settings still work with a deprecation warning.

## Development

Run make check-all to format and lint the code, check types, and run tests. uv is pinned to the same version in Dockerfile and CI; update both together when upgrading uv.
