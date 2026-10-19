"""Talking to Wildberries: a token from the browser, then plain HTTP.

WB authorises its account APIs with a bearer token — a JWT its sign-in SDK
leaves in the page's local storage, good for thirty days. So the browser is
opened once to read that token out of a signed-in profile, closed again, and
every read after it is an ordinary HTTPS request.

That is the whole difference from the Ozon session, which has to keep a browser
alive because its session lives in cookies that rotate on almost every call.
Same problem, different enough answer that sharing one implementation would
have meant writing a switch rather than a session.
"""

import base64
import binascii
import json
import logging
import os
import threading
import time
from atexit import register as register_atexit
from contextlib import suppress
from functools import cache
from pathlib import Path
from typing import Any, Final, Self

from curl_cffi import requests
from playwright.sync_api import Error as PlaywrightError
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from marketplace_mcp.adapters.wildberries.constants import (
    APP_TYPE,
    HOME,
    PURCHASES_PAGE,
    TOKEN_STORAGE_KEY,
)
from marketplace_mcp.core.browser import get_playwright
from marketplace_mcp.core.errors import ErrorCode, MarketplaceError

logger = logging.getLogger(__name__)

# Read the token again this long before it expires rather than at the moment it
# does: a walk that starts valid should not end unauthorised halfway.
_REFRESH_MARGIN_SECONDS: Final = 3600
# 401 is WB refusing the token; 498 is its antibot refusing the cookies. Both
# mean the session read out of the profile is no longer good enough, and both
# are answered the same way — read it again.
_STALE_SESSION: Final = frozenset({401, 498})


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


class WildberriesSession:
    """A bearer token kept fresh from a browser profile, and HTTP that uses it."""

    def __init__(
        self,
        profile_dir: Path | None = None,
        impersonate: str = "chrome124",
        timeout: float = 30.0,
        settings: WildberriesSettings | None = None,
    ) -> None:
        self.settings = settings or WildberriesSettings(
            **({"profile_dir": profile_dir} if profile_dir is not None else {})
        )
        self._profile = self.settings.profile_dir
        self._impersonate = impersonate
        self._timeout = timeout
        self._lock = threading.RLock()
        self._http: Any = None
        self._token: str | None = None
        self._cookies: dict[str, str] = {}
        self._expires_at: float = 0.0
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None

    def _ensure_browser(self) -> None:
        if self._page is not None:
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

    def _read_from_browser(self) -> tuple[str, dict[str, str]]:
        """Open the signed-in profile just long enough to read the session out.

        Both halves are needed, and they are not the same thing. The bearer
        token authorises the caller; the cookies satisfy the antibot in front of
        www.wildberries.ru, which answers 498 without them however good the
        token is. astro.wildberries.ru takes the token alone, which is what made
        the difference easy to miss.

        A login window opened explicitly remains alive until a token appears;
        otherwise a temporary visible browser reads the existing profile and
        closes as soon as the token and cookies have been captured.
        """
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
            cookies: dict[str, str] = {
                str(cookie["name"]): str(cookie["value"])
                for cookie in self._context.cookies()
                if "wildberries" in cookie.get("domain", "") or "wb.ru" in cookie.get("domain", "")
            }
            if not token:
                raise WildberriesSignedOutError(
                    "the profile holds no access token — sign in through wildberries_open_login"
                )
            return str(token), cookies
        finally:
            # Keep an explicitly opened login window alive until credentials
            # exist. A temporary browser is always closed to persist its state.
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
            self._token, self._cookies = self._read_from_browser()
            self._expires_at = self.expiry_of(self._token)
            left = (self._expires_at - time.time()) / 86400
            logger.info("read a Wildberries token, good for %.1f days", left)
            return self._token

    def forget_token(self) -> None:
        """Drop the token so the next call reads a fresh one."""
        with self._lock:
            self._token = None
            self._cookies = {}
            self._expires_at = 0.0

    # -- http ----------------------------------------------------------------

    def _session(self) -> Any:
        if self._http is None:
            self._http = requests.Session(impersonate=self._impersonate)
        return self._http

    def _headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self.token()}",
            "wb-apptype": APP_TYPE,
            "accept-language": "ru-RU",
            "origin": HOME,
            "referer": f"{HOME}/lk/myorders/archive",
        }

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
            if response.status_code in _STALE_SESSION:
                logger.info("Wildberries answered %s; reading the session again", response.status_code)
                self.forget_token()
                response = self._send(method, url, **kwargs)
                if response.status_code in _STALE_SESSION:
                    raise WildberriesSignedOutError(
                        "Wildberries rejected the saved session. Sign in again with wildberries_open_login."
                    )
            if response.status_code >= 400:
                raise WildberriesUpstreamError(
                    f"Wildberries request failed with HTTP {response.status_code}.",
                )
            return response.json()

    def _send(self, method: str, url: str, **kwargs: Any) -> Any:
        headers = self._headers()  # reading these is what fetches the session
        return self._session().request(
            method, url, headers=headers, cookies=self._cookies, timeout=self._timeout, **kwargs
        )

    def close(self) -> None:
        with self._lock:
            self._close_browser()
            if self._http is not None:
                self._http.close()
                self._http = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@cache
def get_session() -> WildberriesSession:
    """One adapter session for this process and its persistent profile."""
    session = WildberriesSession()
    register_atexit(session.close)
    return session
