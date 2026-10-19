"""Read normalized orders back from the shared marketplace store."""

import sqlite3
from typing import Literal

MarketplaceName = Literal["ozon", "wildberries", "yandex_market"]
OrderScope = Literal["all", "active", "completed"]


def list_orders(
    connection: sqlite3.Connection,
    marketplace: MarketplaceName,
    scope: OrderScope = "all",
    limit: int = 100,
) -> list[dict[str, object]]:
    """List stored orders, with each marketplace's original status text."""
    queries = {
        "all": (
            (
                "SELECT order_number, state, status, status_date, paid_total, payment_method "
                "FROM orders WHERE marketplace = ? "
                "ORDER BY COALESCE(status_date, synced_at) DESC, order_number DESC LIMIT ?"
            ),
            (marketplace, limit),
        ),
        "active": (
            (
                "SELECT order_number, state, status, status_date, paid_total, payment_method "
                "FROM orders WHERE marketplace = ? AND state = ? "
                "ORDER BY COALESCE(status_date, synced_at) DESC, order_number DESC LIMIT ?"
            ),
            (marketplace, "active", limit),
        ),
        "completed": (
            (
                "SELECT order_number, state, status, status_date, paid_total, payment_method "
                "FROM orders WHERE marketplace = ? AND state IN (?, ?) "
                "ORDER BY COALESCE(status_date, synced_at) DESC, order_number DESC LIMIT ?"
            ),
            (marketplace, "received", "cancelled", limit),
        ),
    }
    statement, parameters = queries[scope]
    rows = connection.execute(statement, parameters)
    return [dict(row) for row in rows]


def order_details(
    connection: sqlite3.Connection,
    marketplace: MarketplaceName,
    order_number: str,
) -> dict[str, object] | None:
    """Read one normalized order with its parcels and items."""
    order = connection.execute(
        "SELECT order_number, state, status, status_date, paid_total, payment_method "
        "FROM orders WHERE marketplace = ? AND order_number = ?",
        (marketplace, order_number),
    ).fetchone()
    if order is None:
        return None

    parcels: list[dict[str, object]] = []
    for parcel in connection.execute(
        "SELECT shipment_id, status, delivery_kind, delivery_address, recipient "
        "FROM parcels WHERE marketplace = ? AND order_number = ? ORDER BY shipment_id",
        (marketplace, order_number),
    ):
        parcel_data = dict(parcel)
        items = []
        for item in connection.execute(
            "SELECT sku, title, variant, seller, price, received FROM order_items "
            "WHERE marketplace = ? AND order_number = ? AND shipment_id = ? ORDER BY sku",
            (marketplace, order_number, parcel["shipment_id"]),
        ):
            item_data = dict(item)
            if item_data["received"] is not None:
                item_data["received"] = bool(item_data["received"])
            items.append(item_data)
        parcel_data["items"] = items
        parcels.append(parcel_data)
    return {"order": dict(order), "parcels": parcels}
