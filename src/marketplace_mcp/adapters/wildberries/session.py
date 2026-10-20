"""Use Wildberries' signed-in browser profile for its account API.

The buyer API uses a bearer token stored in local storage, but WB's anti-bot
also checks the browser request context. Account reads therefore run as a
same-origin fetch in the persistent browser instead of replaying its token and
cookies through a standalone HTTP client.
"""

import base64
import binascii
import json
import logging
import os
import re
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Final, Self
from urllib.parse import urlencode, urlsplit

from playwright.sync_api import Error as PlaywrightError
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from marketplace_mcp.adapters.wildberries.constants import APP_TYPE, HOME, PURCHASES_PAGE, TOKEN_STORAGE_KEY
from marketplace_mcp.core.browser import get_playwright
from marketplace_mcp.core.dependencies import register_worker_cleanup
from marketplace_mcp.core.errors import ErrorCode, MarketplaceError
from marketplace_mcp.settings import get_server_settings

logger = logging.getLogger(__name__)

# Read the token again this long before it expires rather than at the moment it
# does: a walk that starts valid should not end unauthorised halfway.
_REFRESH_MARGIN_SECONDS: Final = 3600
# A 401 means the browser token is no longer accepted. A 498 is an anti-bot
# block, which should not be misreported as an expired login.
_STALE_SESSION: Final = frozenset({401})
_ANTIBOT_BLOCKED: Final = 498


class WildberriesSignedOutError(MarketplaceError):
    """The stored profile no longer holds a usable token."""

    code = ErrorCode.SESSION_EXPIRED

    def __init__(self, detail: str) -> None:
        super().__init__(f"not signed in to Wildberries: {detail}")


class WildberriesUpstreamError(MarketplaceError):
    """The Wildberries browser or API could not provide a usable response."""

    code = ErrorCode.UPSTREAM

    def __init__(self, message: str) -> None:
        super().__init__(message)


class WildberriesSettings(BaseSettings):
    """Persistent browser profile, kept separate from Ozon's account."""

    model_config = SettingsConfigDict(env_prefix="WILDBERRIES_", extra="ignore")

    profile_dir: Path = Path("/data/wildberries-profile")
    browser_channel: str | None = None
    browser_timeout: float = Field(default=60, gt=0, le=300)


class WildberriesSessionStatus(BaseModel):
    signed_in: bool
    browser_open: bool
    detail: str | None = None


@dataclass(frozen=True)
class _BrowserResponse:
    status_code: int
    body: str

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except json.JSONDecodeError:
            raise WildberriesUpstreamError("Wildberries returned a non-JSON response.") from None


class WildberriesSession:
    """Track token expiry and make account requests in a persistent browser."""

    def __init__(
        self,
        profile_dir: Path | None = None,
        timeout: float = 30.0,
        settings: WildberriesSettings | None = None,
    ) -> None:
        self.settings = settings or WildberriesSettings(
            **({"profile_dir": profile_dir} if profile_dir is not None else {})
        )
        self._profile = self.settings.profile_dir
        self._timeout = timeout
        self._lock = threading.RLock()
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._browser_last_used = 0.0

    def _ensure_browser(self) -> None:
        self._close_idle_browser()
        if self._page is not None:
            self._browser_last_used = time.monotonic()
            return
        self._profile.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self._profile.chmod(0o700)
        from marketplace_mcp.adapters.ozon.constants import LAUNCH_ARGS  # ruff: ignore[import-outside-top-level]

        self._playwright = get_playwright()
        options: dict[str, Any] = {
            "user_data_dir": str(self._profile),
            "headless": False,
            "args": list(LAUNCH_ARGS),
            "locale": "ru-RU",
            "timezone_id": "Europe/Moscow",
            "viewport": {"width": 1366, "height": 900},
        }
        if self.settings.browser_channel:
            options["channel"] = self.settings.browser_channel
        self._context = self._playwright.chromium.launch_persistent_context(**options)
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        self._page.set_default_timeout(self.settings.browser_timeout * 1000)
        self._browser_last_used = time.monotonic()

    def _close_idle_browser(self) -> None:
        if (
            self._context is not None
            and self._browser_last_used > 0
            and get_server_settings().idle_seconds > 0
            and time.monotonic() - self._browser_last_used >= get_server_settings().idle_seconds
        ):
            self._close_browser()

    def open_login(self) -> WildberriesSessionStatus:
        """Open a visible persistent profile and leave it available for sign-in."""
        with self._lock:
            try:
                self._ensure_browser()
                if not (self._page.url or "").startswith(HOME) or "/lk/mypurchases" not in self._page.url:
                    self._page.goto(PURCHASES_PAGE, wait_until="domcontentloaded")
            except (PlaywrightError, OSError):
                self._close_browser()
                raise WildberriesUpstreamError(
                    "Could not open the Wildberries sign-in browser. Check the browser installation and retry.",
                ) from None
            return WildberriesSessionStatus(
                signed_in=False,
                browser_open=True,
                detail="Browser opened. Sign in to Wildberries there, then call wildberries_session_status.",
            )

    def status(self) -> WildberriesSessionStatus:
        """Check that the profile contains an unexpired session token."""
        with self._lock:
            try:
                self.token()
            except WildberriesSignedOutError:
                return WildberriesSessionStatus(
                    signed_in=False,
                    browser_open=self._page is not None,
                    detail="No usable session token. Call wildberries_open_login and sign in in the browser.",
                )
            return WildberriesSessionStatus(
                signed_in=True,
                browser_open=self._page is not None,
                detail="Profile contains an unexpired session token; upstream access is checked on the next read.",
            )

    def _close_browser(self) -> None:
        # Another adapter may still be using the shared Playwright driver.
        with suppress(Exception):
            if self._context is not None:
                self._context.close()
        self._context = self._page = self._playwright = None

    # -- the token -----------------------------------------------------------

    def _read_from_browser(self) -> str:
        """Read the current bearer token from the signed-in profile."""
        opened_here = self._context is None
        token: str | None = None
        try:
            if opened_here and not (self._profile / "Default").exists():
                raise WildberriesSignedOutError(
                    f"no Wildberries browser profile at {self._profile}; call wildberries_open_login first"
                )
            self._ensure_browser()
            if not (self._page.url or "").startswith(HOME):
                self._page.goto(
                    PURCHASES_PAGE,
                    wait_until="domcontentloaded",
                    timeout=self.settings.browser_timeout * 1000,
                )
            if opened_here:
                self._page.wait_for_timeout(6_000)
            token_value: Any = self._page.evaluate(f"() => localStorage.getItem({TOKEN_STORAGE_KEY!r})")
            token = str(token_value) if token_value else None
            if not token:
                raise WildberriesSignedOutError(
                    "the profile holds no access token — sign in through wildberries_open_login"
                )
            return str(token)
        finally:
            # Keep an explicitly opened login window alive until credentials
            # exist. A temporary browser is always closed after reading the token.
            if token or opened_here:
                self._close_browser()

    @staticmethod
    def expiry_of(token: str) -> float:
        """When a token stops being accepted, from its own claims.

        Read rather than assumed: the alternative is finding out mid-walk, and
        the claim is right there. A token that cannot be read at all is treated
        as expiring now, which sends the caller back to the browser.
        """
        try:
            payload = token.split(".")[1]
            padded = payload + "=" * (-len(payload) % 4)
            return float(json.loads(base64.urlsafe_b64decode(padded))["exp"])
        except (IndexError, ValueError, KeyError, binascii.Error):
            logger.warning("could not read the token's expiry; treating it as expired")
            return 0.0

    def token(self) -> str:
        """The current token, fetched from the browser if there is not one."""
        with self._lock:
            if self._token and time.time() < self._expires_at - _REFRESH_MARGIN_SECONDS:
                return self._token
            self._token = self._read_from_browser()
            self._expires_at = self.expiry_of(self._token)
            left = (self._expires_at - time.time()) / 86400
            logger.info("read a Wildberries token, good for %.1f days", left)
            return self._token

    def forget_token(self) -> None:
        """Drop the token so the next call reads a fresh one."""
        with self._lock:
            self._token = None
            self._expires_at = 0.0

    # -- browser-backed API transport ---------------------------------------

    def get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        return self._call("GET", url, params=params)

    def post(self, url: str, body: Any = None) -> Any:
        return self._call("POST", url, json=body if body is not None else {})

    def _call(self, method: str, url: str, **kwargs: Any) -> Any:
        """One request, retried once if the stored session turned out to be stale.

        Only once, and only on the two answers that mean exactly that: anything
        else is the caller's problem, and a second browser launch for a server
        error would cost a minute to learn nothing.
        """
        with self._lock:
            response = self._send(method, url, **kwargs)
            if response.status_code == _ANTIBOT_BLOCKED:
                raise WildberriesUpstreamError(
                    "Wildberries blocked the authenticated browser request with its anti-bot protection."
                )
            if response.status_code in _STALE_SESSION:
                logger.info("Wildberries answered %s; reading the session again", response.status_code)
                self.forget_token()
                response = self._send(method, url, **kwargs)
                if response.status_code in _STALE_SESSION:
                    raise WildberriesSignedOutError(
                        "Wildberries rejected the browser session. Sign in again with wildberries_open_login."
                    )
                if response.status_code == _ANTIBOT_BLOCKED:
                    raise WildberriesUpstreamError(
                        "Wildberries blocked the authenticated browser request with its anti-bot protection."
                    )
            if response.status_code >= 400:
                raise WildberriesUpstreamError(
                    f"Wildberries request failed with HTTP {response.status_code}.",
                )
            return response.json()

    def _send(self, method: str, url: str, **kwargs: Any) -> _BrowserResponse:
        """Make the account request from the signed-in browser's own origin.

        WB's web API returns HTTP 498 to a standalone HTTP client even when it
        has the profile's valid bearer token and cookies. A same-origin fetch
        keeps the browser's cookies and request fingerprint together.
        """
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != urlsplit(HOME).netloc:
            raise ValueError("Wildberries account requests must stay on the Wildberries origin.")
        params = kwargs.get("params")
        if params:
            query = urlencode(params, doseq=True)
            url = f"{url}{'&' if parsed.query else '?'}{query}"
        body = kwargs.get("json")
        body_text = json.dumps(body, ensure_ascii=False, separators=(",", ":")) if body is not None else None

        with self._lock:
            try:
                self._ensure_browser()
                response = (
                    self._capture_orders_page(url)
                    if parsed.path == "/api/v2/orders"
                    else self._send_from_page(
                        method,
                        url,
                        body_text,
                    )
                )
            except PlaywrightError as exc:
                self._close_browser()
                detail = str(exc).splitlines()[0][:240]
                detail = re.sub(r"(?i)Bearer\s+\S+", "Bearer <redacted>", detail)
                detail = re.sub(r"https?://\S+", "<url>", detail)
                logger.warning("Wildberries browser request failed with %s: %s", type(exc).__name__, detail)
                raise WildberriesUpstreamError(
                    f"Could not complete the request in the Wildberries browser ({type(exc).__name__})."
                ) from None
            else:
                self._browser_last_used = time.monotonic()
                return response

    def _send_from_page(self, method: str, url: str, body: str | None) -> _BrowserResponse:
        """Run an account request with the profile's browser credentials."""
        if "/lk/mypurchases" not in (self._page.url or ""):
            self._page.goto(
                PURCHASES_PAGE,
                wait_until="domcontentloaded",
                timeout=self.settings.browser_timeout * 1000,
            )
        result = self._page.evaluate(
            r"""async ({url, method, body, tokenKey, appType, timeoutMs}) => {
              const token = localStorage.getItem(tokenKey);
              if (!token) return {status: 401, body: ""};
              const headers = {
                authorization: `Bearer ${token}`,
                "accept-language": "ru-RU"
              };
              if (new URL(url).pathname !== "/api/v2/orders") headers["wb-apptype"] = appType;
              const deviceId = localStorage.getItem("wbx__sessionID");
              if (deviceId) headers.deviceid = deviceId;
              const wbauid = document.cookie
                .split(";")
                .map(part => part.trim())
                .find(part => part.startsWith("_wbauid="))
                ?.slice("_wbauid=".length);
              if (wbauid) headers.wbauid = decodeURIComponent(wbauid);
              if (body !== null) headers["content-type"] = "application/json";
              const controller = new AbortController();
              const timer = setTimeout(() => controller.abort(), timeoutMs);
              try {
                const response = await fetch(url, {
                  method, headers, body: body === null ? undefined : body,
                  credentials: "include", signal: controller.signal
                });
                return {status: response.status, body: await response.text()};
              } finally {
                clearTimeout(timer);
              }
            }""",
            {
                "url": url,
                "method": method.upper(),
                "body": body,
                "tokenKey": TOKEN_STORAGE_KEY,
                "appType": APP_TYPE,
                "timeoutMs": round(self._timeout * 1000),
            },
        )
        return _BrowserResponse(status_code=int(result["status"]), body=str(result.get("body") or ""))

    def _capture_orders_page(self, url: str) -> _BrowserResponse:
        """Capture the account page's own first-page orders XHR.

        WB returns HTML when this endpoint is replayed from the same page
        context. Listening to the request made during page load preserves the
        browser's exact request behavior.
        """
        page = self._page
        path = urlsplit(url).path
        pattern = f"**{path}*"

        def continue_request(route: Any) -> None:
            route.continue_()

        def is_target(response: Any) -> bool:
            return urlsplit(str(response.url)).path == path

        try:
            page.route(pattern, continue_request)
            with page.expect_response(is_target, timeout=self.settings.browser_timeout * 1000) as captured:
                page.goto(
                    PURCHASES_PAGE,
                    wait_until="domcontentloaded",
                    timeout=self.settings.browser_timeout * 1000,
                )
            response = captured.value
            return _BrowserResponse(status_code=response.status, body=response.text())
        except PlaywrightError:
            raise WildberriesUpstreamError(
                "Could not read the orders list from the Wildberries account page."
            ) from None
        finally:
            with suppress(PlaywrightError):
                page.unroute(pattern, continue_request)

    def close(self) -> None:
        with self._lock:
            self._close_browser()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@cache
def get_session() -> WildberriesSession:
    """One adapter session for this process and its persistent profile."""
    session = WildberriesSession()
    register_worker_cleanup(session.close)
    return session
