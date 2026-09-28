"""A named search refusal keeps console words separate from page keys."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.json_value import JsonValue
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.search_refusal_reason import SearchRefusalReason


class SearchRefusalError(NotFoundError):
    """A search refusal the page must render with its own catalog."""

    def __init__(self, source_key: str, page_key: str, **values: JsonValue) -> None:
        super().__init__(phrase(source_key, **values))
        self.reason = SearchRefusalReason(page_key, dict(values))


class SearchRefusalInfraError(InfraError):
    """An infrastructure refusal whose page reason is still known."""

    def __init__(self, source_key: str, page_key: str, **values: JsonValue) -> None:
        super().__init__(phrase(source_key, **values))
        self.reason = SearchRefusalReason(page_key, dict(values))


__all__ = ["SearchRefusalError", "SearchRefusalInfraError"]
