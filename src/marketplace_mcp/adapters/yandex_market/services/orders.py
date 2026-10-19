"""Read Yandex Market buyer orders from the authenticated frontend resolver."""

from typing import Literal

from marketplace_mcp.adapters.yandex_market.models.orders import YandexMarketOrderGroup
from marketplace_mcp.adapters.yandex_market.parsing.orders import _bad_response, parse_page
from marketplace_mcp.adapters.yandex_market.session import get_session


def list_orders(scope: Literal["active", "completed"], limit: int) -> list[YandexMarketOrderGroup]:
    if scope not in {"active", "completed"} or not 1 <= limit <= 1000:
        raise ValueError("Expected active/completed scope and limit between 1 and 1000")
    session = get_session()
    rows: dict[str, YandexMarketOrderGroup] = {}
    token = None
    seen_tokens: set[str] = set()
    for _ in range(100):
        page, next_token = parse_page(session.page(scope, token), scope)
        for row in page:
            rows[row.group_id] = row
        if len(rows) >= limit or not next_token:
            return list(rows.values())[:limit]
        if next_token in seen_tokens:
            raise _bad_response()
        seen_tokens.add(next_token)
        token = next_token
    raise _bad_response()
