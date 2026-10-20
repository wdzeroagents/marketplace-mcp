from pathlib import Path
from typing import Any

from marketplace_mcp.adapters.wildberries.source import WildberriesSource
from marketplace_mcp.core.store import connect, read
from marketplace_mcp.core.store.sync import sync_orders


class FakeSession:
    def get(self, _url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"data": []}

    def post(self, _url: str, _body: Any) -> dict[str, Any]:
        return {
            "value": {
                "archive": [
                    {
                        "orderId": "wb-order-1",
                        "code1S": 123456,
                        "name": "Jacket",
                        "brand": "Brand",
                        "size": "M",
                        "color": "blue",
                        "rawPrice": 123456,
                        "status": "Purchased",
                        "orderDate": "2026-10-10T10:00:00Z",
                        "lastDate": "2026-10-11T10:00:00Z",
                        "officeId": 211648,
                        "sellerId": 17,
                        "paymentType": "CARD",
                    }
                ]
            }
        }


class NoImages:
    def find(self, _nm_id: int) -> str | None:
        return None


class Offices:
    def address(self, office_id: int | None) -> str | None:
        return "Sample pickup point" if office_id == 211648 else None

    def kind(self, office_id: int | None) -> str:
        return "Доставка в пункт выдачи" if office_id == 211648 else "Доставка курьером"


def test_wildberries_orders_sync_to_shared_store_and_read_back(tmp_path: Path) -> None:
    connection = connect(tmp_path / "store.db")
    source = WildberriesSource(FakeSession(), images=NoImages(), offices=Offices())
    try:
        report = sync_orders(connection, source, full=True)
        orders = read.list_orders(connection, "wildberries", "completed")
        details = read.order_details(connection, "wildberries", "wb-order-1")
        missing = read.order_details(connection, "ozon", "wb-order-1")
    finally:
        connection.close()

    assert report.orders_read == 1
    assert report.parcels_read == 1
    assert orders == [
        {
            "order_number": "wb-order-1",
            "state": "received",
            "status": "Purchased",
            "status_date": "2026-10-11",
            "paid_total": "1 234,56 ₽",
            "payment_method": "CARD",
        }
    ]
    assert details is not None
    assert details["parcels"][0]["delivery_address"] == "Sample pickup point"
    assert details["parcels"][0]["items"][0]["received"] is True
    assert missing is None
