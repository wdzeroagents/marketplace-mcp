from typing import Final

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

"""Prometheus instrumentation shared by the marketplace adapters."""


METRICS_PATH: Final = "/metrics"

UPSTREAM_REQUESTS: Final = Counter(
    "marketplace_mcp_upstream_requests_total",
    "Requests to a marketplace, by backend and outcome.",
    ["backend", "outcome"],
)

UPSTREAM_LATENCY: Final = Histogram(
    "marketplace_mcp_upstream_request_seconds",
    "Latency of requests to a marketplace.",
    ["backend"],
)

SESSION_BOOTSTRAPS: Final = Counter(
    "marketplace_mcp_session_bootstraps_total",
    "Browser bootstraps performed to clear the antibot and harvest a session.",
    ["reason"],
)

BROWSER_ACTIVE: Final = Gauge(
    "marketplace_mcp_browser_active",
    "1 while a Chromium instance is held open, 0 when only HTTP is live.",
)


def metrics_endpoint(_request: Request) -> Response:
    """Scrape endpoint; sync so Starlette runs the blocking encode off the loop."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
