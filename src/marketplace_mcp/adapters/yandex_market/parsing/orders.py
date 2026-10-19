"""Parse the observed Yandex Market order resolver response."""

from typing import Any, Literal

from marketplace_mcp.adapters.yandex_market.models.orders import YandexMarketOrderGroup
from marketplace_mcp.adapters.yandex_market.session import YandexMarketError
from marketplace_mcp.core.errors import ErrorCode


def _bad_response() -> YandexMarketError:
    return YandexMarketError(ErrorCode.UPSTREAM, "Yandex Market order response is incomplete or has changed.")


def _page_groups(page: dict[str, Any], groups: dict[str, Any]) -> tuple[list[Any], str | None]:
    token = page.get("pageToken")
    if token is not None and not isinstance(token, str):
        raise _bad_response()
    group_ids = page.get("ordersGroupsIds")
    if group_ids is None:
        if "emptyState" in page and not groups and not token:
            return [], None
        raise _bad_response()
    if not isinstance(group_ids, list):
        raise _bad_response()
    return group_ids, token or None


def parse_page(
    answer: dict[str, Any], scope: Literal["active", "completed"]
) -> tuple[list[YandexMarketOrderGroup], str | None]:
    results = answer.get("results")
    if answer.get("error") or not isinstance(results, list) or len(results) != 1:
        raise _bad_response()
    result = results[0]
    if not isinstance(result, dict) or result.get("error") or not isinstance(result.get("data"), dict):
        raise _bad_response()
    data = result["data"]
    collections = data.get("collections")
    ids = data.get("result")
    if not isinstance(collections, dict) or not isinstance(ids, list) or len(ids) != 1:
        raise _bad_response()
    pages = collections.get("orderConsolidationResult")
    if not isinstance(pages, dict) or not isinstance(ids[0], str):
        raise _bad_response()
    page = pages.get(ids[0])
    if not isinstance(page, dict):
        raise _bad_response()
    groups = collections.get("orderConsolidationGroup", {})
    if not isinstance(groups, dict):
        raise _bad_response()
    group_ids, token = _page_groups(page, groups)
    rows = []
    for group_id in group_ids:
        if not isinstance(group_id, str) or not isinstance(groups.get(group_id), dict):
            raise _bad_response()
        rows.append(_parse_group(group_id, groups[group_id], scope))
    return rows, token


def _parse_group(group_id: str, group: dict[str, Any], scope: Literal["active", "completed"]) -> YandexMarketOrderGroup:
    numbers = group.get("orderIds")
    if (
        not isinstance(numbers, list)
        or not numbers
        or any(
            isinstance(n, bool) or not isinstance(n, (str, int)) or not str(n).isascii() or not str(n).isdigit()
            for n in numbers
        )
    ):
        raise _bad_response()
    title = group.get("title", [])
    if not isinstance(title, list):
        raise _bad_response()
    status = "".join(
        part["value"]
        for part in title
        if isinstance(part, dict) and part.get("type") == "TEXT" and isinstance(part.get("value"), str)
    )
    return YandexMarketOrderGroup(
        group_id=group_id,
        order_numbers=[str(number) for number in numbers],
        scope=scope,
        status=status or None,
        detail_links=[f"https://market.yandex.ru/my/order/{number}" for number in numbers],
    )
