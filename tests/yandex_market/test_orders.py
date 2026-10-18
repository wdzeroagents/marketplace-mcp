from typing import Any
from unittest.mock import Mock

import pytest

from marketplace_mcp.adapters.yandex_market import orders
from marketplace_mcp.adapters.yandex_market.session import YandexMarketError


def page(ids: list[str], token: str | None = None) -> dict[str, Any]:
    return {
        "results": [
            {
                "data": {
                    "result": ["page"],
                    "collections": {
                        "orderConsolidationResult": {"page": {"ordersGroupsIds": ids, "pageToken": token}},
                        "orderConsolidationGroup": {
                            key: {"orderIds": [123, "456"], "title": [{"type": "TEXT", "value": "В сборке"}]}
                            for key in ids
                        },
                    },
                }
            }
        ]
    }


def test_reads_only_referenced_groups() -> None:
    data = page(["group"])
    data["results"][0]["data"]["collections"]["orderConsolidationGroup"]["unrelated"] = {}
    rows, token = orders.parse_page(data, "active")
    assert token is None
    assert len(rows) == 1
    assert rows[0].order_numbers == ["123", "456"]
    assert rows[0].status == "В сборке"
    assert rows[0].detail_links == ["https://market.yandex.ru/my/order/123", "https://market.yandex.ru/my/order/456"]


def test_empty_account_is_explicit() -> None:
    assert orders.parse_page(page([]), "active") == ([], None)


def test_empty_state_resolver_page_is_an_empty_account() -> None:
    data = page([])
    collections = data["results"][0]["data"]["collections"]
    collections["orderConsolidationResult"]["page"] = {"selectedTab": "ACTIVE", "emptyState": {}}
    assert orders.parse_page(data, "active") == ([], None)


@pytest.mark.parametrize(
    "answer", [{}, {"results": []}, {"results": [{"error": "secret"}]}, {"results": [{"data": {}}]}]
)
def test_failure_is_not_an_empty_account(answer: dict[str, Any]) -> None:
    with pytest.raises(YandexMarketError, match="upstream_unavailable") as error:
        orders.parse_page(answer, "active")
    assert "secret" not in str(error.value)


def test_missing_group_fails() -> None:
    data = page(["missing"])
    data["results"][0]["data"]["collections"]["orderConsolidationGroup"] = {}
    with pytest.raises(YandexMarketError):
        orders.parse_page(data, "active")


def test_pagination_deduplicates_and_preserves_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock()
    session.page.side_effect = [page(["one"], "next"), page(["one", "two", "three"])]
    monkeypatch.setattr(orders, "get_session", lambda: session)
    rows = orders.list_orders("completed", 2)
    assert [row.group_id for row in rows] == ["one", "two"]
    assert rows[0].scope == "completed"
    assert session.page.call_args_list[1].args == ("completed", "next")


def test_cursor_loop_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock()
    session.page.return_value = page(["one"], "loop")
    monkeypatch.setattr(orders, "get_session", lambda: session)
    with pytest.raises(YandexMarketError):
        orders.list_orders("active", 100)
    assert session.page.call_count == 2


@pytest.mark.parametrize("number", [True, {}, "https://other.example", "１２３"])
def test_invalid_order_identifiers_are_rejected(number: Any) -> None:
    data = page(["one"])
    data["results"][0]["data"]["collections"]["orderConsolidationGroup"]["one"]["orderIds"] = [number]
    with pytest.raises(YandexMarketError):
        orders.parse_page(data, "active")
