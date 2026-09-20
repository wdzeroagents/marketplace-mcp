"""Direct HTTPS using operator-provided session credentials, never tool arguments."""

from functools import cache
from typing import Any

from curl_cffi import requests
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from marketplace_mcp.core.errors import ErrorCode, MarketplaceError

HOME = "https://market.yandex.ru"
RESOLVER = HOME + "/api/resolve/?r=src/resolvers/orders/resolveConsolidationOrders:resolveConsolidationOrders"


class YandexMarketError(MarketplaceError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class YandexMarketSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YANDEX_MARKET_", extra="ignore")

    session_id: SecretStr = SecretStr("")
    sk: SecretStr = SecretStr("")
    request_timeout: float = Field(default=30, gt=0, le=120)


class YandexMarketSession:
    def __init__(self, settings: YandexMarketSettings) -> None:
        self.settings = settings

    def page(self, scope: str, token: str | None = None) -> dict[str, Any]:
        if scope not in {"active", "completed"}:
            raise ValueError("Scope must be active or completed")
        session_id = self.settings.session_id.get_secret_value()
        sk = self.settings.sk.get_secret_value()
        if not session_id or not sk:
            raise YandexMarketError(
                ErrorCode.SESSION_EXPIRED, "Configure YANDEX_MARKET_SESSION_ID and YANDEX_MARKET_SK."
            )
        if any(char in session_id + sk for char in "\r\n") or ";" in session_id:
            raise YandexMarketError(ErrorCode.SESSION_EXPIRED, "Invalid Yandex Market credential format.")
        path = "/my/orders" + ("?filter=COMPLETED" if scope == "completed" else "")
        params: dict[str, Any] = {"filter": scope.upper(), "size": 20}
        if token:
            params["pageToken"] = token
        try:
            response = requests.post(
                RESOLVER,
                headers={"sk": sk, "Origin": HOME, "Referer": HOME + path},
                cookies={"Session_id": session_id},
                json={"params": [params], "path": path},
                timeout=self.settings.request_timeout,
                allow_redirects=False,
                impersonate="chrome124",
            )
        except requests.RequestsError:
            raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market request failed; retry later.") from None
        return _read_response(response)


def _read_response(response: Any) -> dict[str, Any]:
    if response.status_code in {401, 403}:
        raise YandexMarketError(
            ErrorCode.SESSION_EXPIRED,
            "Yandex Market rejected the session or sk; sign in again and update both credentials. "
            "An access challenge may also cause this response.",
        )
    if response.status_code == 429:
        raise YandexMarketError(ErrorCode.RATE_LIMITED, "Yandex Market rate limit; retry later.")
    if response.status_code != 200:
        raise YandexMarketError(ErrorCode.UPSTREAM, f"Yandex Market returned HTTP {response.status_code}.")
    try:
        answer = response.json()
    except ValueError:
        raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market returned invalid JSON.") from None
    if not isinstance(answer, dict):
        raise YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market returned an unexpected response.")
    return answer


@cache
def get_session() -> YandexMarketSession:
    return YandexMarketSession(YandexMarketSettings())
