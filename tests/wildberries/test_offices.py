from typing import Any
from unittest.mock import Mock

from marketplace_mcp.adapters.wildberries.constants import WAREHOUSE_ID_FROM
from marketplace_mcp.adapters.wildberries.offices import PickupPoints


def response(data: Any) -> Mock:
    result = Mock()
    result.json.return_value = data
    return result


def test_reads_public_directory_and_infers_delivery_kind() -> None:
    session = Mock()
    session.get.return_value = response([{"items": [{"id": 123, "address": "Sample street"}]}])
    points = PickupPoints(session)
    assert points.address(123) == "Sample street"
    assert points.kind(123) == "Доставка в пункт выдачи"
    assert points.kind(WAREHOUSE_ID_FROM) == "Доставка курьером"
    session.get.assert_called_once()


def test_missing_and_malformed_directory_rows_are_ignored() -> None:
    session = Mock()
    session.get.return_value = response([
        None,
        "not-a-group",
        {"items": None},
        {"items": [None, {}, {"id": "bad", "address": "x"}, {"id": 4}]},
    ])
    points = PickupPoints(session)
    assert points.address(4) is None


def test_unavailable_directory_is_cached_as_empty() -> None:
    session = Mock()
    session.get.side_effect = OSError("unavailable")
    points = PickupPoints(session)
    assert points.address(123) is None
    assert points.address(124) is None
    session.get.assert_called_once()
