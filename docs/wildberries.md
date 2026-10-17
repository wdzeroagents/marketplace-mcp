# Wildberries source adapter

The Wildberries adapter is implemented as `WildberriesSource` and maps the
account archive into the shared core records for purchases, orders, and
parcels. It reads the account through the JSON APIs used by the Wildberries
site. A signed-in Chromium profile supplies the bearer token and cookies; the
token is refreshed from that profile when it is missing or close to expiry.

## Current integration status

This is a source-level adapter, not a set of user-facing MCP tools. The current
server does not construct or register `WildberriesSource`, and there is no
Wildberries profile setting or sync command wired into the application. The
adapter's behavior is covered by unit tests using a stand-in session. Do not
expect Wildberries data to appear through the running MCP server yet.

The shared core can synchronize a `MarketplaceSource`, but the registered store
tools currently construct `OzonSource` directly. A future integration needs to
add Wildberries profile configuration and an explicit way to select or run that
source before it is available through MCP.
