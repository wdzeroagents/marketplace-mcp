from pathlib import Path
from unittest.mock import Mock

import pytest

from marketplace_mcp.adapters.yandex_market import orders
from marketplace_mcp.adapters.yandex_market.source import YandexMarketSource
from marketplace_mcp.core.store import connect
from marketplace_mcp.core.store.read import list_orders, order_details
from marketplace_mcp.core.store.sync import sync_orders


def test_yandex_orders_and_order_items_sync_into_shared_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = orders.YandexMarketOrderGroup(
        group_id="group-1",
        order_numbers=["987654321"],
        scope="completed",
        status="Получен 18 октября",
        detail_links=["https://market.yandex.ru/my/order/987654321"],
    )
    monkeypatch.setattr(orders, "list_orders", lambda scope, limit: [group] if scope == "completed" else [])
    browser = Mock()
    browser.order_detail.return_value = {
        "status": "Получен 18 октября",
        "paid_total": "1 299",
        "items": [{"sku": "123456", "title": "Чай", "price": "1 299"}],
    }
    source = YandexMarketSource(browser)
    connection = connect(tmp_path / "store.sqlite")
    try:
        report = sync_orders(connection, source, full=True)
        listed = list_orders(connection, "yandex_market")
        detail = order_details(connection, "yandex_market", "987654321")
    finally:
        connection.close()

    assert report.orders_read == 1
    assert listed[0]["state"] == "received"
    assert listed[0]["status"] == "Получен 18 октября"
    assert detail is not None
    assert detail["parcels"][0]["shipment_id"] == "yandex-order:987654321"
    assert detail["parcels"][0]["items"][0]["sku"] == "123456"
    assert detail["parcels"][0]["items"][0]["title"] == "Чай"
    browser.order_detail.assert_called_once_with("987654321")

