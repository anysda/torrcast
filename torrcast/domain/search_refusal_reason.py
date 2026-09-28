"""A search refusal reason the page can render."""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain.json_value import JsonValue


@dataclass(frozen=True, slots=True)
class SearchRefusalReason:
    """A page-catalog key and the values it needs."""

    key: str
    values: dict[str, JsonValue]

    def json(self) -> dict[str, JsonValue]:
        """Return the response object read by the page."""
        return {"key": self.key, "values": self.values}


def reason_of(error: Exception) -> SearchRefusalReason:
    """Return the named reason or the honest generic external failure."""
    from torrcast.domain.search_refusal_error import SearchRefusalError, SearchRefusalInfraError

    if isinstance(error, SearchRefusalError | SearchRefusalInfraError):
        return error.reason
    return SearchRefusalReason("web.search.failed", {})


__all__ = ["SearchRefusalReason", "reason_of"]
