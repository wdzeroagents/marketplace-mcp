from collections.abc import Iterable
from pathlib import Path

import pytest

from marketplace_mcp.core.records import OrderRecord, OrderState, ParcelRecord, ProductRecord
from marketplace_mcp.core.store import connect, writes
from marketplace_mcp.core.store.sync import sync_orders


class Source:
    name = "example"

    def __init__(self) -> None:
        self.parcels_read: list[str] = []

    def orders(self, _limit: int) -> list[OrderRecord]:
        return [
            OrderRecord(number="new", state=OrderState.ACTIVE),
            OrderRecord(number="known", state=OrderState.RECEIVED),
            OrderRecord(number="old", state=OrderState.RECEIVED),
        ]

    def parcels(self, order_number: str) -> list[ParcelRecord]:
        self.parcels_read.append(order_number)
        return []

    def purchases(self, _limit: int) -> Iterable[ProductRecord]:
        return []


def test_incremental_walk_stops_at_settled_order_but_full_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = connect(tmp_path / "store.db")
    at = writes.now()
    writes.save_order(connection, "example", OrderRecord(number="known", state=OrderState.RECEIVED), at)
    connection.commit()
    monkeypatch.setattr("marketplace_mcp.core.store.sync.writes.now", iter(("one", "two", "three", "four")).__next__)
    source = Source()
    try:
        report = sync_orders(connection, source)
        assert report.stopped_at == "known"
        assert source.parcels_read == ["new"]

        source.parcels_read.clear()
        report = sync_orders(connection, source, full=True)
        assert report.stopped_at is None
        assert source.parcels_read == ["new", "known", "old"]
    finally:
        connection.close()
