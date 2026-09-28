"""A named infrastructure refusal preserves its page reason."""

from __future__ import annotations

from torrcast.domain.reason_of import reason_of
from torrcast.domain.search_refusal_infra_error import SearchRefusalInfraError


def test_a_named_infrastructure_error_keeps_its_page_reason() -> None:
    refused = SearchRefusalInfraError(
        "discover.prowlarr_not_configured", "web.search.prowlarr_not_configured"
    )

    assert reason_of(refused).key == "web.search.prowlarr_not_configured"
