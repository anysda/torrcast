"""A named search refusal keeps console words separate from page keys."""

from __future__ import annotations

from torrcast.domain._search_refusal_reason import _SearchReason
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.json_value import JsonValue
from torrcast.domain.not_found_error import NotFoundError


class SearchRefusalError(NotFoundError):
    """A search refusal the page must render with its own catalog."""

    def __init__(self, source_key: str, page_key: str, **values: JsonValue) -> None:
        super().__init__(phrase(source_key, **values))
        self.reason = _SearchReason(page_key, dict(values))


__all__ = ["SearchRefusalError"]
