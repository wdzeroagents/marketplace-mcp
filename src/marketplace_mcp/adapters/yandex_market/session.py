"""Authenticated Yandex Market session backed by a persistent browser profile."""

import atexit
import json
import os
import threading
from contextlib import suppress
from functools import cache
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError, sync_playwright
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from marketplace_mcp.core.errors import ErrorCode, MarketplaceError

HOME = "https://market.yandex.ru"
ORDERS_PATH = "/my/orders"
RESOLVER = "/api/resolve/?r=src/resolvers/orders/resolveConsolidationOrders:resolveConsolidationOrders"
_RESOLVER_SCRIPT = """
async ({endpoint, payload}) => {
  const findSk = () => document.documentElement.outerHTML.match(/[\\\"']sk[\\\"']\\s*:\\s*[\\\"']([^\\\"']+)[\\\"']/i);
  let match = findSk();
  const deadline = Date.now() + 5000;
  while (!match && Date.now() < deadline) {
    await new Promise(resolve => setTimeout(resolve, 100));
    match = findSk();
  }
  if (!match) return {status: 0, error: "session_parameter_missing"};
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: {"content-type": "application/json", sk: match[1]},
      body: JSON.stringify(payload)
    });
    return {status: response.status, text: await response.text()};
  } catch (_) {
    return {status: 0, error: "request_failed"};
  }
}
"""


class YandexMarketError(MarketplaceError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class YandexMarketSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YANDEX_MARKET_", extra="ignore")

    profile_dir: Path = Path("/data/yandex-market-profile")
    browser_timeout: float = Field(default=60, gt=0, le=300)
    browser_channel: str | None = None


class YandexMarketSessionStatus(BaseModel):
    signed_in: bool
    browser_open: bool
    detail: str | None = None


class YandexMarketSession:
    """A single browser profile owns the cookies and request-only `sk` value."""

    def __init__(self, settings: YandexMarketSettings | None = None) -> None:
        self.settings = settings or YandexMarketSettings()
        self._lock = threading.RLock()
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None

    def _ensure_browser(self) -> None:
        if self._page is not None:
            return
        self.settings.profile_dir.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.settings.profile_dir.chmod(0o700)
        self._playwright = sync_playwright().start()
        options: dict[str, Any] = {
            "user_data_dir": str(self.settings.profile_dir),
            "headless": False,
            "locale": "ru-RU",
            "timezone_id": "Asia/Yekaterinburg",
            "viewport": {"width": 1366, "height": 900},
        }
        if self.settings.browser_channel:
            options["channel"] = self.settings.browser_channel
        self._context = self._playwright.chromium.launch_persistent_context(**options)
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        self._page.set_default_timeout(self.settings.browser_timeout * 1000)

    def open_login(self) -> YandexMarketSessionStatus:
        """Open the persistent browser at the buyer orders page for sign-in."""
        with self._lock:
            try:
                self._ensure_browser()
                if not (self._page.url or "").startswith(HOME) or "/my/orders" not in (self._page.url or ""):
                    self._page.goto(HOME + ORDERS_PATH, wait_until="domcontentloaded")
            except PlaywrightError:
                self.close()
                raise YandexMarketError(
                    ErrorCode.UPSTREAM,
                    "Could not open the Yandex Market sign-in browser. Check the browser installation and retry.",
                ) from None
            return YandexMarketSessionStatus(
                signed_in=False,
                browser_open=True,
                detail=(
                    "Browser opened. Sign in to Yandex Market there, complete any challenge, "
                    "then call yandex_market_session_status."
                ),
            )

    def status(self) -> YandexMarketSessionStatus:
        """Check the session with the same authenticated resolver used for reads."""
        with self._lock:
            try:
                self.page("active")
            except YandexMarketError as exc:
                if exc.code is ErrorCode.SESSION_EXPIRED:
                    return YandexMarketSessionStatus(
                        signed_in=False,
                        browser_open=self._page is not None,
                        detail=(
                            "Session is not ready. Call yandex_market_open_login, sign in in the browser, "
                            "then check again."
                        ),
                    )
                raise
            return YandexMarketSessionStatus(
                signed_in=True,
                browser_open=True,
                detail="Yandex Market session is ready.",
            )

    def page(self, scope: str, token: str | None = None) -> dict[str, Any]:
        if scope not in {"active", "completed"}:
            raise ValueError("Scope must be active or completed")
        path = ORDERS_PATH + ("?filter=COMPLETED" if scope == "completed" else "")
        params: dict[str, Any] = {"filter": scope.upper(), "size": 20}
        if token:
            params["pageToken"] = token
        with self._lock:
            try:
                self._ensure_browser()
                self._page.goto(HOME + path, wait_until="domcontentloaded")
                result = self._page.evaluate(
                    _RESOLVER_SCRIPT,
                    {"endpoint": RESOLVER, "payload": {"params": [params], "path": path}},
                )
            except PlaywrightError:
                raise YandexMarketError(
                    ErrorCode.UPSTREAM, "Yandex Market browser request failed; retry later."
                ) from None
        if not isinstance(result, dict):
            raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market returned an unexpected browser response.")
        status = result.get("status")
        if status in {401, 403} or result.get("error") == "session_parameter_missing":
            raise YandexMarketError(
                ErrorCode.SESSION_EXPIRED,
                "Yandex Market session is signed out or challenged. Call yandex_market_open_login "
                "and complete sign-in in the browser.",
            )
        if status == 429:
            raise YandexMarketError(ErrorCode.RATE_LIMITED, "Yandex Market rate limit; retry later.")
        if status != 200 or not isinstance(result.get("text"), str):
            raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market request failed; retry later.")
        try:
            answer = json.loads(result["text"])
        except ValueError:
            raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market returned invalid JSON.") from None
        if not isinstance(answer, dict):
            raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market returned an unexpected response.")
        return answer

    def close(self) -> None:
        """Flush and close the browser profile at process shutdown."""
        with self._lock:
            for obj, method in ((self._context, "close"), (self._playwright, "stop")):
                with suppress(Exception):
                    if obj is not None:
                        getattr(obj, method)()
            self._playwright = self._context = self._page = None


@cache
def get_session() -> YandexMarketSession:
    session = YandexMarketSession()
    atexit.register(session.close)
    return session
