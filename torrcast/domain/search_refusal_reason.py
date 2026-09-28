"""Turn a search exception into the page reason it can render."""

from __future__ import annotations

from torrcast.domain._search_refusal_reason import _SearchReason
from torrcast.domain.search_refusal_error import SearchRefusalError


def _reason_of(error: Exception) -> _SearchReason:
    """Return the named reason or the honest generic external failure."""
    if isinstance(error, SearchRefusalError):
        return error.reason
    return _SearchReason("web.search.failed", {})


__all__ = ["_reason_of"]
