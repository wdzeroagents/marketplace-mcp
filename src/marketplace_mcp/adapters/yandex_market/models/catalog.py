"""Catalog data returned by the Yandex Market buyer tools."""

from pydantic import BaseModel, ConfigDict, Field


class YandexMarketTile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_id: str
    title: str
    price: str | None = Field(default=None, description="The price shown on the search tile, in roubles.")
    url: str
    image: str | None = None
    rating: float | None = None
    reviews_count_display: str | None = Field(
        default=None, description="The compact review count shown on the search tile, when present."
    )


class YandexMarketProduct(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_id: str
    title: str
    price: str | None = None
    currency: str | None = None
    available: bool | None = None
    rating: float | None = None
    reviews_count: int | None = None
    description: str | None = None
    image: str | None = None
    url: str
