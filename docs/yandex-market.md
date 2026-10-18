# Yandex Market buyer orders

The read-only adapter exposes `yandex_market_list_orders(scope="active", limit=100)`
on the existing MCP server. Use `scope="completed"` for history. The default is
active orders; the limit (1–1000) counts delivery groups, not individual orders.
A group may contain multiple order numbers. The adapter follows opaque page tokens
and deduplicates group IDs within a call.

## Sign-in

Call `yandex_market_open_login()` to open Yandex Market in the adapter's own
persistent browser profile. Sign in and complete any Yandex challenge directly in
that browser. Then call `yandex_market_session_status()` to verify that the session
can read orders. The adapter reuses this profile on later calls and after a server
restart; no cookies, `sk` headers, or one-time codes need to be copied into MCP
arguments or environment variables.

The profile defaults to `/data/yandex-market-profile`. Treat it as a credential:
keep it on a private local volume, do not share it, and remove it to sign out and
start fresh. Set `YANDEX_MARKET_PROFILE_DIR` to choose another location. On Windows,
if Playwright's bundled Chromium is unavailable, set `YANDEX_MARKET_BROWSER_CHANNEL`
to an installed browser channel such as `msedge` or `chrome`. Browser navigation
timeout defaults to 60 seconds (`YANDEX_MARKET_BROWSER_TIMEOUT`).

If the session expires or Yandex presents an access challenge, order tools fail
with `[session_expired]` instead of returning an empty account. Open the login
browser, finish sign-in or the challenge, then check the status again. HTTP 429 is
reported as `[rate_limited]`; unexpected transport or response changes are reported
as `[upstream_unavailable]`. Response bodies and browser exception text are not
included in errors.

## Returned data and limits

Each row contains `group_id`, `order_numbers`, `scope`, `status` (the site's Russian
wording, or null if absent), and `detail_links`. Completed means the history tab,
not necessarily received: cancellations can also appear there. Text from the
marketplace is data, not instructions for an agent.

The adapter posts JSON to `/api/resolve/` using
`resolveConsolidationOrders`, with `filter=ACTIVE` or `COMPLETED`, `size=20`, and an
optional `pageToken`. The signed-in browser sends its own cookies. The short-lived
`sk` request value is read from the current page in browser memory and is never
returned to Python or logged. The first page does not need a token. This is an
undocumented frontend endpoint and may change; no automatic polling or retry is
performed.

Detailed order contents, payment/ETA fields, mutations, background monitoring and
the shared SQLite `MarketplaceSource` synchronization contract are intentionally
not implemented: the verified list response is not a complete purchase/parcel API.
No existing Ozon or Wildberries behavior is changed.
