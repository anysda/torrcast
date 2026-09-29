"""Картина нашлась, а раздач нужного сезона в ней нет."""

from __future__ import annotations

from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.domain.search_refusal_error import SearchRefusalError
from torrcast.usecases.choice._named import _title


def _no_season(picture: Picture, episode: Episode | None) -> SearchRefusalError:
    """Отказ со своими словами: какая картина и какого сезона в её раздачах нет.

    Серии в запросе нет - отказ называет первый сезон, как и прежде в круге поиска.
    """
    want = episode or Episode(1, 1)
    return SearchRefusalError(
        "discover.no_season_releases",
        "web.search.no_season_releases",
        title=_title(picture),
        season=want.season,
    )
