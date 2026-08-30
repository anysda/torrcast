"""English captions of the prowlarr cluster."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Return the English catalog of the prowlarr cluster."""
    return {
        "prowlarr.unexpected_answer": "Prowlarr returned an unexpected answer",
        "prowlarr.all_indexers_unavailable": (
            "Prowlarr moved every indexer to unavailable ({names}) - no catalog right now"
        ),
        "prowlarr.selected_indexers_unresponsive": "Prowlarr: the chosen indexers do not answer",
        "prowlarr.unresponsive": "Prowlarr does not answer ({base_url}): {reason}",
        "prowlarr.not_json": "Prowlarr returned something other than JSON",
    }
