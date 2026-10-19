"""Yandex Market order models."""

from typing import Literal

from pydantic import BaseModel


class YandexMarketOrderGroup(BaseModel):
    group_id: str
    order_numbers: list[str]
    scope: Literal["active", "completed"]
    status: str | None = None
    detail_links: list[str]
