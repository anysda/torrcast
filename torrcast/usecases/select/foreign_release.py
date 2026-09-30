"""Раздача пула, которую отбор не спрашивает: она не про эту картину или не про эту серию."""

from __future__ import annotations

from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.rank.foreign_reason import foreign_reason


def foreign_release(release: Release, picture: Picture, want: Episode | None) -> bool:
    """Не наша раздача: кино другого года или нужной серии в ней нет (:func:`foreign_reason`).

    Серии нет, когда имя её не обещает, или раздача другой работы франшизы, или более
    поздней формы. Причину тем же судом называет счёт отсева: правило одно, и очередь с
    объяснением отказа разойтись не могут.
    """
    return bool(foreign_reason(release, picture, want))


__all__ = ["foreign_release"]
