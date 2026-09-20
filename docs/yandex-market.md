# Yandex Market buyer orders

The optional read-only adapter exposes `yandex_market_list_orders(scope="active", limit=100)`
on the existing MCP server. Use `scope="completed"` for history. No Ozon login is required.
The default is active orders; the limit (1–1000) counts delivery groups, not individual orders.
A group may contain multiple order numbers. The adapter follows opaque page tokens and
deduplicates group IDs within a call. It makes fresh requests on every invocation.

## Configuration

Supply `YANDEX_MARKET_SESSION_ID` (the value of the `Session_id` cookie) and
`YANDEX_MARKET_SK` (the `sk` request header) from the same signed-in buyer session,
through the server process environment or your local secret manager. Do not paste
credentials into MCP conversations, put them in command-line arguments or commit them.
`YANDEX_MARKET_REQUEST_TIMEOUT` defaults to 30 seconds per page.

To locate the values locally, sign into market.yandex.ru in a dedicated browser profile,
open DevTools Network, then the completed orders list and “Показать ещё”. Inspect the
request whose resolver is `src/resolvers/orders/resolveConsolidationOrders`.
The values must stay on the operator's machine. This module does not import browser profiles.

After replacing credentials, restart the MCP process: its settings are cached.
No fixed credential lifetime is assumed and automatic renewal is not implemented.
HTTP 401/403 reports `[session_expired]` (an access challenge can also produce 403);
429 reports `[rate_limited]`. Other HTTP/transport/schema errors report
`[upstream_unavailable]`. Errors never masquerade as an empty account, and upstream
response bodies and transport exception text are not exposed in error messages.

## Returned data and limits

Each row contains `group_id`, `order_numbers`, `scope`, `status` (the site's Russian
wording, or null if absent), and `detail_links`. Completed means the history tab,
not necessarily received: cancellations can also appear there. Text is data from
the marketplace, not instructions for an agent.

The adapter posts JSON to `/api/resolve/` using `resolveConsolidationOrders`, with
`filter=ACTIVE` or `COMPLETED`, `size=20`, and an optional `pageToken`. The first
page does not need a token. It does not parse HTML or launch a browser for reads.
This is an undocumented frontend endpoint and may change. No retries are made
automatically, so callers should back off on throttling and avoid frequent polling.

Detailed order contents, payment/ETA fields, mutations, background monitoring and
the shared SQLite `MarketplaceSource` synchronization contract are intentionally
not implemented: the verified list response is not a complete purchase/parcel API.
No existing Ozon or Wildberries behavior is changed.

The endpoint, first-page reads, active orders, and the `Session_id` + `sk` credential
combination were verified in a separate live investigation. Adapter unit tests use
synthetic fixtures; no real account data or credentials belong in the repository.

The Python adapter itself was also smoke-tested against a signed-in account: one
active group and twenty completed groups were parsed successfully, with a continuation
token for history. This does not establish long-term session renewal or API stability.
