"""Английские надписи кластера перехода через границу сезона."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера перехода через границу сезона."""
    return {
        "season.searching_next": (
            "«{title}» - season {season} watched, searching season {upcoming}"
        ),
        "season.no_next_found": "«{title}» - season {season} was the last: {err}",
        "season.search_failed": "«{title}» - season {upcoming} could not be searched: {err}",
        "season.no_releases_found": (
            "«{title}» - season {season} was the last: no releases for season {upcoming} were found"
        ),
        "season.could_not_start": "«{title}» - season {upcoming} could not start: {err}",
    }
