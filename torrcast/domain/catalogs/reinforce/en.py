"""Английский каталог кластера доборов каталога."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера доборов каталога."""
    return {
        "reinforce.year_mismatch": (
            "the catalogue holds a {found_year} picture under this name, not "
            "{about_year} - there's no other one there"
        ),
        "reinforce.refine_reason": "refine by “{name}”",
        "reinforce.search_phase": "search “{name}”",
        "reinforce.year_unknown": "year unknown",
        "reinforce.ceiling_note": (
            "by “{name}” results hit the catalogue's ceiling, and the picture "
            "itself isn't in it - topped up via “{refined}”: “{title}” ({year})"
        ),
        "reinforce.late_indexer": "late indexer",
        "reinforce.arrived_after_list": "“{who}” arrived after the list: ",
        "reinforce.foreign_brought": "brought {names} - ",
        "reinforce.and_more": " and {n} more",
        "reinforce.not_listed_singular": "it wasn't in the list, so it won't be picked",
        "reinforce.not_listed_plural": "they weren't in the list, so they won't be picked",
        "reinforce.season_reason": "top up season {season}",
        "reinforce.season_note": (
            "season {season} was missing from the results - topped up via “{query}”"
        ),
        "reinforce.topup_counts": "releases {now} instead of {was}",
        "reinforce.topup_changed": ", the pick at the top changed",
        "reinforce.voice_reason": "top up via “{exact}”",
        "reinforce.voice_note": (
            "“{title}” has Russian only where nothing can play it - "
            "topped up via “{exact}”: releases now {now}"
        ),
    }
