"""Правило «раздача кино другого года - раздача другой картины»."""

from __future__ import annotations

from torrcast.domain.own_release import YEAR_SLACK
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def other_year(release: Release, picture: Picture) -> bool:
    """Раздача кино названа годом, от которого год картины дальше :data:`YEAR_SLACK`.

    «Оно» 2017 года и «Оно приходит за тобой / It Follows [2014]» по-русски зовутся
    одинаково, и склейка по имени может положить их в один пул. Играть вторую вместо
    первой - подмена картины, и отбор её не спрашивает вовсе: отказ честнее.

    Не судится то, чего не знаем: раздача без года в имени, картина без года. Не судится
    и сериал: сезон датирован своим годом, и год начала от него законно отстоит на годы.
    """
    if picture.kind != "movie" or picture.year is None or release.year is None:
        return False
    return abs(release.year - picture.year) > YEAR_SLACK


__all__ = ["other_year"]
