# Wildberries buyer adapter

The Wildberries adapter reads both the active-order list and the buyer's
purchase archive through the JSON APIs used by the site, then writes normalized
orders, parcels, and items to the shared store. Active orders are synced first
so an older completed purchase cannot stop the scan before them.

## Sign in

Call `wildberries_open_login()` and sign in in the browser window it opens. Then
call `wildberries_session_status()`. Account requests run as same-origin fetches
inside the adapter's persistent browser context, so the token and anti-bot
cookies stay in that profile and are not copied into MCP arguments, results, or
logs. `session_expired` means WB rejected the token; an HTTP 498 response is
reported as an anti-bot/upstream block rather than a sign-out.

The profile defaults to `/data/wildberries-profile` and can be changed with
`WILDBERRIES_PROFILE_DIR`. Set `WILDBERRIES_BROWSER_CHANNEL` to `msedge` or
`chrome` to use an installed browser. To sign out completely, stop the server
and remove that profile directory. An idle context is closed lazily after
`MARKETPLACE_IDLE_SECONDS` (default 600); the timeout is checked on the next
browser operation, which reopens the saved profile.

## Tools

- `wildberries_sync_orders(full=false, limit=1000)` stores order status, dates,
  parcels, delivery destinations, payment method, and items. WB's active API
  provides numeric state codes rather than display text; those orders remain
  active in the shared store and the code is kept in the status field. Settled
  archive orders are skipped on routine runs; active and unfamiliar statuses
  are read again. Use `full=true` for a first sync or a complete refresh.
- `wildberries_sync_prices(limit=1000)` stores the amounts WB reports in purchase
  history. These are historical amounts paid, not current catalogue prices.
- `marketplace_orders(marketplace="wildberries", scope="all")` lists the
  synchronized orders. `scope` can be `active` or `completed`.
- `marketplace_order_details(marketplace="wildberries", order_number=...)`
  returns a stored order with its parcels and item details.

The store path is shared with every adapter and configured through
`MARKETPLACE_STORE_PATH` (default `/data/store.db`). Marketplace IDs are part of every key, so equal
order numbers or product IDs from different marketplaces do not overwrite one
another.

## Data and limitations

WB's archive has one row per purchased item and does not expose a parcel ID. The
adapter groups items from one order by destination; this is the finest parcel
grouping the endpoint supports. It maps known delivered, returned, cancelled,
and failed-payment archive statuses into the common state. Unknown archive
statuses stay active so later syncs can pick up a changed interpretation. A
returned item has `received=false` because it is no longer owned. The active
orders API does not provide the archive's text status; its numeric state is
recorded verbatim and the order remains active until it appears settled in the
archive.

The archive gives the price paid at purchase time, while Ozon's price sync reads
today's catalogue price. Do not compare those series as if they measured the
same thing. WB does not expose a buyer-side product description endpoint through
this adapter; details here are the order's recorded product, variant, seller,
and delivery data.
