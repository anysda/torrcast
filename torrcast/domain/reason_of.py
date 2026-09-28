"""Choose the page reason for a search exception."""

from __future__ import annotations

from torrcast.domain.search_refusal_error import SearchRefusalError
from torrcast.domain.search_refusal_infra_error import SearchRefusalInfraError
from torrcast.domain.search_refusal_reason import SearchRefusalReason


def reason_of(error: Exception) -> SearchRefusalReason:
    """Return the named reason or the honest generic external failure."""
    if isinstance(error, SearchRefusalError | SearchRefusalInfraError):
        return error.reason
    return SearchRefusalReason("web.search.failed", {})


__all__ = ["reason_of"]
