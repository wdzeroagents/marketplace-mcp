"""Common Yandex Market buyer DTOs."""

from pydantic import BaseModel


class YandexMarketWriteResult(BaseModel):
    ok: bool = True
    detail: str | None = None
