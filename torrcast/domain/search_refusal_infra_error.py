"""An infrastructure search refusal with a page reason."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.json_value import JsonValue
from torrcast.domain.search_refusal_reason import SearchRefusalReason


class SearchRefusalInfraError(InfraError):
    """An infrastructure refusal whose page reason is still known."""

    def __init__(self, source_key: str, page_key: str, **values: JsonValue) -> None:
        super().__init__(phrase(source_key, **values))
        self.reason = SearchRefusalReason(page_key, dict(values))


__all__ = ["SearchRefusalInfraError"]
