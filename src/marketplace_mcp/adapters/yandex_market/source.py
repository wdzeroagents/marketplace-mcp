"""Yandex Market orders, expressed in the shared store's records."""

from collections.abc import Iterable
from typing import Literal

from marketplace_mcp.adapters.yandex_market import orders
from marketplace_mcp.adapters.yandex_market.session import YandexMarketSession, get_session
from marketplace_mcp.core.records import OrderRecord, OrderState, ParcelItemRecord, ParcelRecord, ProductRecord


class YandexMarketSource:
    """Read buyer orders through the signed-in persistent browser profile."""

    name = "yandex_market"

    def __init__(self, session: YandexMarketSession | None = None) -> None:
        self.session = session or get_session()

    def purchases(self, limit: int) -> list[ProductRecord]:
        """Yandex's order pages do not expose the Ozon-style purchase catalogue."""
        del limit
        return []

    def orders(self, limit: int) -> Iterable[OrderRecord]:
        if not 1 <= limit <= 1000:
            raise ValueError("Expected an order limit between 1 and 1000")
        seen: set[str] = set()
        count = 0
        scopes: tuple[Literal["active"], Literal["completed"]] = ("active", "completed")
        for scope in scopes:
            for group in orders.list_orders(scope, limit):
                for number in group.order_numbers:
                    if number in seen:
                        continue
                    seen.add(number)
                    yield OrderRecord(
                        number=number,
                        state=_state(group.status, scope),
                        status=group.status,
                    )
                    count += 1
                    if count >= limit:
                        return

    def parcels(self, order_number: str) -> list[ParcelRecord]:
        detail = self.session.order_detail(order_number)
        items = [
            ParcelItemRecord(
                sku=str(item["sku"]),
                title=_optional_text(item.get("title")),
                price=_optional_text(item.get("price")),
            )
            for item in detail["items"]
            if item.get("sku") is not None
        ]
        # The buyer detail page exposes order items but no stable shipment id.
        # Keep them readable in the common parcel-shaped store with an explicit
        # namespaced order key rather than inventing a Yandex shipment number.
        return [
            ParcelRecord(
                order_number=order_number,
                shipment_id=f"yandex-order:{order_number}",
                status=_optional_text(detail.get("status")),
                paid_total=_optional_text(detail.get("paid_total")),
                items=items,
            )
        ]


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _state(status: str | None, scope: str) -> OrderState:
    text = (status or "").casefold()
    if any(word in text for word in ("отмен", "возвращ", "не выкуп")):
        return OrderState.CANCELLED
    if any(word in text for word in ("получен", "доставлен", "выдан")):
        return OrderState.RECEIVED
    if scope == "completed":
        # Unknown completed wording is preserved verbatim but stays re-readable
        # until we have a confirmed final-state mapping for that wording.
        return OrderState.ACTIVE
    return OrderState.ACTIVE
