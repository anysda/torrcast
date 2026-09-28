"""Named search refusals keep console words separate from page keys."""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.json_value import JsonValue
from torrcast.domain.not_found_error import NotFoundError


@dataclass(frozen=True, slots=True)
class SearchReason:
    """An English page key and the values it must render."""

    key: str
    values: dict[str, JsonValue]

    def json(self) -> dict[str, JsonValue]:
        """Return the JSON sent in a refusal response."""
        return {"key": self.key, "values": self.values}


class SearchRefusal(NotFoundError):
    """A search refusal the page must render with its own catalog."""

    def __init__(self, source_key: str, page_key: str, **values: JsonValue) -> None:
        super().__init__(phrase(source_key, **values))
        self.reason = SearchReason(page_key, dict(values))


def reason_of(error: Exception) -> SearchReason:
    """Return the named reason or the honest generic external failure."""
    if isinstance(error, SearchRefusal):
        return error.reason
    return SearchReason("web.search.failed", {})


__all__ = ["SearchReason", "SearchRefusal", "reason_of"]
