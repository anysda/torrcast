"""Раздача своим именем признаётся, что нужной серии в ней нет; зовут ворота и порядок."""

from __future__ import annotations

from torrcast.domain.episode import Episode
from torrcast.domain.release import Release


def misses_episode(release: Release, want: Episode | None) -> bool:
    """Раздача сама, своим именем, признаётся, что нужной серии в ней нет.

    Первая ступень порядка и единственная, которая стоит выше образов дисков: релиз без
    нужной серии не «хуже качеством», а бесполезен — играть в нём нечего. Молчаливое
    имя сюда не попадает никогда (:meth:`Release.covers_episode`), поэтому у сериала,
    где серии не перечисляет ни одно имя, порядок остаётся прежним.
    """
    return want is not None and not release.covers_episode(want)
