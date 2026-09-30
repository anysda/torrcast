"""Раздача пула, которую отбор не спрашивает: она не про эту картину или не про эту серию."""

from __future__ import annotations

from torrcast.domain.episode import Episode
from torrcast.domain.foreign_work import foreign_work
from torrcast.domain.later_form import later_form
from torrcast.domain.other_year import other_year
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.rank.misses_episode import misses_episode


def foreign_release(release: Release, picture: Picture, want: Episode | None) -> bool:
    """Не наша раздача: кино другого года (:func:`other_year`) или нужной серии в ней нет.

    Серии нет, когда имя её не обещает (:func:`misses_episode`), или раздача другой
    работы франшизы (:func:`foreign_work`), или более поздней формы (:func:`later_form`).
    """
    return (
        other_year(release, picture)
        or misses_episode(release, want)
        or (
            want is not None
            and (foreign_work(release, picture) or later_form(release, picture, want))
        )
    )


__all__ = ["foreign_release"]
