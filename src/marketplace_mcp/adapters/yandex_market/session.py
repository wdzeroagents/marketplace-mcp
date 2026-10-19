"""Authenticated Yandex Market session backed by a persistent browser profile."""

import atexit
import json
import os
import threading
from contextlib import suppress
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from playwright.sync_api import Error as PlaywrightError
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from marketplace_mcp.core.browser import get_playwright
from marketplace_mcp.core.errors import ErrorCode, MarketplaceError

HOME = "https://market.yandex.ru"
ORDERS_PATH = "/my/orders"
RESOLVER = "/api/resolve/?r=src/resolvers/orders/resolveConsolidationOrders:resolveConsolidationOrders"
SEARCH_PATH = "/search?text="
PRODUCT_CARD_PATH = "/card/"
WISHLIST_ADD_ENDPOINT = "/api/web/market.front.wishlist.Wishlist/addWishlistItem"
WISHLIST_DELETE_ENDPOINT = "/api/web/market.front.wishlist.Wishlist/deleteWishlistItem"
CART_ADD_ENDPOINT = "/api/web/market.front.purchaseCore.PurchaseCore/prepareCartModelAddItems"
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
_SEARCH_SCRIPT = """
({limit}) => {
  const normalize = value => (value || '').replace(/\\s+/g, ' ').trim();
  const pricePattern = /(?:Цена[^\\d]{0,40})?([\\d\\s\\u00a0]+(?:[,.]\\d{1,2})?)\\s*₽/;
  const grouped = new Map();
  for (const link of document.querySelectorAll('a[data-auto="snippet-link"]')) {
    let path;
    try { path = new URL(link.href).pathname; } catch (_) { continue; }
    const id = path.match(/\\/(\\d+)\\/?$/)?.[1];
    if (!id || !path.startsWith('/card/')) continue;
    if (!grouped.has(path)) grouped.set(path, {path, id, links: []});
    grouped.get(path).links.push(link);
  }
  const out = [];
  for (const item of grouped.values()) {
    const titleLink = item.links
      .map(link => ({link, text: normalize(link.innerText)}))
      .filter(x => x.text && !/^(Цена|Рейтинг|Оценок|Купить|В корзину)/i.test(x.text))
      .sort((a, b) => b.text.length - a.text.length)[0];
    if (!titleLink) continue;
    let card = titleLink.link;
    for (let i = 0; i < 8 && card; i++, card = card.parentElement) {
      if ((card.innerText || '').includes('₽')) break;
    }
    const text = normalize(card?.innerText);
    const price = text.match(pricePattern)?.[1]?.replace(/[\\s\\u00a0]+/g, ' ')?.trim() || null;
    const rating = text.match(/Рейтинг товара:\\s*([\\d,.]+)/i)?.[1]?.replace(',', '.') || null;
    const count = text.match(/Оценок:\\s*\\(?([\\d,.\\s]+(?:K|К)?)\\)?/i)?.[1]?.trim() || null;
    const image = card?.querySelector('img')?.currentSrc || card?.querySelector('img')?.src || null;
    out.push({
      product_id: item.id, title: titleLink.text, price,
      url: location.origin + item.path, image, rating, reviews_count: count
    });
    if (out.length >= limit) break;
  }
  return out;
}
"""
_PRODUCT_SCRIPT = """
() => {
  const values = [];
  for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const parsed = JSON.parse(script.textContent || 'null');
      values.push(...(Array.isArray(parsed) ? parsed : [parsed]));
    } catch (_) {}
  }
  const queue = [...values];
  let product = null;
  while (queue.length) {
    const value = queue.shift();
    if (!value || typeof value !== 'object') continue;
    const types = Array.isArray(value['@type']) ? value['@type'] : [value['@type']];
    if (types.some(type => String(type).toLowerCase() === 'product')) { product = value; break; }
    if (Array.isArray(value['@graph'])) queue.push(...value['@graph']);
  }
  if (!product) return null;
  const offers = Array.isArray(product.offers) ? product.offers[0] : product.offers;
  const rating = product.aggregateRating || {};
  const image = Array.isArray(product.image) ? product.image[0] : product.image;
  const id = location.pathname.match(/\\/(\\d+)\\/?$/)?.[1] || null;
  const available = typeof offers?.availability === 'string'
    ? /instock|limitedavailability/i.test(offers.availability)
    : null;
  return {
    product_id: id,
    title: product.name || document.querySelector('h1')?.innerText?.trim() || null,
    description: typeof product.description === 'string' ? product.description : null,
    price: offers?.price != null ? String(offers.price) : null,
    currency: offers?.priceCurrency || null,
    available,
    rating: Number.isFinite(Number(rating.ratingValue)) ? Number(rating.ratingValue) : null,
    reviews_count: Number.isFinite(Number(rating.ratingCount)) ? Number(rating.ratingCount) : null,
    image: typeof image === 'string' ? image : image?.url || null,
    url: location.origin + location.pathname
  };
}
"""
_FAVORITE_STATE_SCRIPT = """
() => {
  const button = document.querySelector('button[data-auto="wishlist"]');
  if (!button) return null;
  const label = (button.innerText || '').trim();
  const title = button.title || '';
  return {favorite: /удалить из избранного/i.test(title) || /в избранном/i.test(label)};
}
"""
_CART_CONTAINS_SCRIPT = """
({product_id, title}) => {
  const id = String(product_id);
  const linked = [...document.querySelectorAll('a[href*="/card/"]')].some(anchor => {
    try { return new URL(anchor.href).pathname.match(/\\/(\\d+)\\/?$/)?.[1] === id; }
    catch (_) { return false; }
  });
  return linked || Boolean(title && (document.body?.innerText || '').includes(title));
}
"""
_ORDER_DETAIL_SCRIPT = r"""
() => {
  const norm = value => (value || '').replace(/\\s+/g, ' ').trim();
  const page = document.querySelector('[data-auto="order-page"]');
  const details = document.querySelector('[data-auto="order-details"]');
  if (!page || !details) return null;
  const statusPattern = new RegExp(
    "получен|доставлен|отмен[её]н|возвращ[её]н|в пути|сборк|ожидает|" +
    "передан курьеру|готов к выдаче",
    "i"
  );
  const status = [...details.querySelectorAll('*')]
    .filter(element => element.children.length === 0)
    .map(element => norm(element.innerText))
    .find(text => text && text.length < 180 && statusPattern.test(text)) || null;
  const items = [...details.querySelectorAll('[data-auto="order-item"]')].map(item => {
    const links = [...item.querySelectorAll('a[href*="/card/"]')];
    const link = links.find(anchor => /\\/\\d+\\/?$/.test(new URL(anchor.href).pathname));
    let sku = null;
    let url = null;
    if (link) {
      const path = new URL(link.href).pathname;
      sku = path.match(/\\/(\\d+)\\/?$/)?.[1] || null;
      url = location.origin + path;
    }
    const title = links.map(anchor => norm(anchor.innerText)).find(text => text && text.length > 2) || null;
    const text = norm(item.innerText);
    const pricePattern = /([\\d\\s\\u00a0]+(?:[,.]\\d{1,2})?)\\s*₽/;
    const price = text.match(pricePattern)?.[1]?.replace(/[\\s\\u00a0]+/g, ' ')?.trim() || null;
    return {sku, title, url, price};
  }).filter(item => item.sku || item.title);
  const body = norm(details.innerText);
  const totalLine = body.split(/(?=Итого)/i).find(line => /^Итого/i.test(line));
  const totalPattern = /([\\d\\s\\u00a0]+(?:[,.]\\d{1,2})?)\\s*₽/;
  const paidTotal = totalLine?.match(totalPattern)?.[1]?.replace(/[\\s\\u00a0]+/g, ' ')?.trim() || null;
  return {status, items, paid_total: paidTotal};
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
    enable_writes: bool = False


class YandexMarketSessionStatus(BaseModel):
    signed_in: bool
    browser_open: bool
    writes_enabled: bool = False
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
        self._playwright = get_playwright()
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
                writes_enabled=self.settings.enable_writes,
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
                        writes_enabled=self.settings.enable_writes,
                        detail=(
                            "Session is not ready. Call yandex_market_open_login, sign in in the browser, "
                            "then check again."
                        ),
                    )
                raise
            return YandexMarketSessionStatus(
                signed_in=True,
                browser_open=True,
                writes_enabled=self.settings.enable_writes,
                detail="Yandex Market session is ready.",
            )

    def search_page(self, query: str, limit: int) -> list[dict[str, Any]]:
        if not query.strip() or len(query) > 200 or not 1 <= limit <= 16:
            raise ValueError("Expected non-empty search text (up to 200 characters) and limit between 1 and 16")
        path = SEARCH_PATH + quote(query.strip(), safe="")
        with self._lock:
            self._navigate(path)
            result = self._page.evaluate(_SEARCH_SCRIPT, {"limit": limit})
        if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
            raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market search results are incomplete or have changed.")
        return result

    def product_page(self, path: str) -> dict[str, Any]:
        if not path.startswith(PRODUCT_CARD_PATH) or ".." in path or "?" in path or "#" in path:
            raise ValueError("Expected a clean Yandex Market product-card path")
        with self._lock:
            self._navigate(path)
            result = self._page.evaluate(_PRODUCT_SCRIPT)
        if not isinstance(result, dict):
            raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market product details are incomplete or have changed.")
        return result

    def product_favorite_state(self, path: str) -> bool | None:
        with self._lock:
            self._navigate(path)
            result = self._page.evaluate(_FAVORITE_STATE_SCRIPT)
        if isinstance(result, dict):
            favorite = result.get("favorite")
            if isinstance(favorite, bool):
                return favorite
        return None

    def set_product_favorite(self, path: str, *, add: bool) -> bool:
        endpoint = WISHLIST_ADD_ENDPOINT if add else WISHLIST_DELETE_ENDPOINT
        with self._lock:
            self._navigate(path)
            state = self._page.evaluate(_FAVORITE_STATE_SCRIPT)
            current = state.get("favorite") if isinstance(state, dict) else None
            if current is None:
                raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market favorite control is missing or has changed.")
            if current is add:
                return True
            try:
                with self._page.expect_response(lambda response: endpoint in response.url) as response_info:
                    self._page.locator('button[data-auto="wishlist"]').first.click()
            except PlaywrightError:
                raise YandexMarketError(
                    ErrorCode.UPSTREAM, "Yandex Market favorite change was not confirmed."
                ) from None
            self._check_mutation_status(response_info.value.status)
            state = self._page.evaluate(_FAVORITE_STATE_SCRIPT)
            confirmed = state.get("favorite") if isinstance(state, dict) else None
            return confirmed is add

    def add_product_to_cart(self, path: str, product_id: str, title: str) -> bool:
        with self._lock:
            self._navigate("/my/cart")
            present = self._page.evaluate(_CART_CONTAINS_SCRIPT, {"product_id": product_id, "title": title})
            if present is True:
                return True
            self._navigate(path)
            try:
                with self._page.expect_response(lambda response: CART_ADD_ENDPOINT in response.url) as response_info:
                    self._page.locator('button[data-auto="cartButton"]').first.click()
            except PlaywrightError:
                raise YandexMarketError(
                    ErrorCode.UPSTREAM, "Yandex Market did not confirm adding this product to cart."
                ) from None
            self._check_mutation_status(response_info.value.status)
            self._navigate("/my/cart")
            present = self._page.evaluate(_CART_CONTAINS_SCRIPT, {"product_id": product_id, "title": title})
            return present is True

    def _navigate(self, path: str) -> None:
        try:
            self._ensure_browser()
            self._page.goto(HOME + path, wait_until="domcontentloaded")
            current_path = self._page.url or ""
            title = self._page.title() or ""
        except PlaywrightError:
            raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market browser request failed; retry later.") from None
        if "/showcaptcha" in current_path or "не робот" in title.lower() or "/auth" in current_path:
            raise YandexMarketError(
                ErrorCode.SESSION_EXPIRED,
                "Yandex Market session needs sign-in or a manual access challenge. "
                "Call yandex_market_open_login() and finish it in the browser.",
            )

    @staticmethod
    def _check_mutation_status(status: int) -> None:
        if status in {401, 403}:
            raise YandexMarketError(
                ErrorCode.SESSION_EXPIRED,
                "Yandex Market session needs sign-in or a manual access challenge. "
                "Call yandex_market_open_login() and finish it in the browser.",
            )
        if status == 429:
            raise YandexMarketError(ErrorCode.RATE_LIMITED, "Yandex Market rate limit; retry later.")
        if not 200 <= status < 300:
            raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market rejected the change; retry later.")

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

    def order_detail(self, order_number: str) -> dict[str, Any]:
        """Read the buyer order's SSR detail page without exposing profile data."""
        if not order_number.isascii() or not order_number.isdigit() or len(order_number) > 32:
            raise ValueError("Expected a numeric Yandex Market order number")
        with self._lock:
            self._navigate(f"/my/order/{quote(order_number, safe='')}")
            result = self._page.evaluate(_ORDER_DETAIL_SCRIPT)
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            raise YandexMarketError(
                ErrorCode.UPSTREAM,
                "Yandex Market order details are incomplete or have changed.",
            )
        if any(not isinstance(item, dict) for item in result["items"]):
            raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market order items are incomplete or have changed.")
        return result

    def close(self) -> None:
        """Flush and close the browser profile at process shutdown."""
        with self._lock:
            # Another adapter may still be using the shared Playwright driver.
            with suppress(Exception):
                if self._context is not None:
                    self._context.close()
            self._playwright = self._context = self._page = None


@cache
def get_session() -> YandexMarketSession:
    session = YandexMarketSession()
    atexit.register(session.close)
    return session
