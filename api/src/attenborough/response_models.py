from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel


class Message(BaseModel):
    detail: str

    @staticmethod
    def for_statuses(
        statuses: Iterable[int],
    ) -> dict[int | str, dict[str, type[Message]]]:
        return {status: {"model": Message} for status in statuses}


class GoogleLoginLocation(BaseModel):
    url: str


class ExhibitMeta(BaseModel):
    """What exhibit clients need to know about the API, such as its page sizes."""

    default_page_take: int
    max_page_take: int
