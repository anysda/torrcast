"""Зеркало :mod:`torrcast.usecases.choice.carries_season`: несёт ли картина спрошенный сезон.

Вынесен из :mod:`torrcast.usecases.choice.asked_season` под TC-860: та же проверка нужна
и честной строке выбора (:func:`~torrcast.usecases.choice.default_note.default_note`),
не только сужению меню перед ней.
"""

from __future__ import annotations

from dataclasses import replace

from tests.usecases.choice.world import film
from torrcast.domain.picture import Picture
from torrcast.usecases.choice.carries_season import carries_season


def test_a_picture_without_a_part_number_carries_every_season() -> None:
    """Часть не названа - картина несёт любой сезон: цифры для сверки просто нет."""
    picture = Picture(title="Ход королевы", year=2020, kind="tv")

    assert carries_season(picture, 1) is True
    assert carries_season(picture, 5) is True


def test_a_matching_part_number_carries_its_own_season() -> None:
    """Часть картины совпала со спрошенным сезоном - несёт его."""
    picture = Picture(title="Код Гиас: Восставший Лелуш 2", year=2008, kind="tv", part=2)

    assert carries_season(picture, 2) is True


def test_a_mismatched_part_number_is_rescued_by_a_release_that_names_the_season() -> None:
    """🔴 TC-856. Часть чужая, но раздача сама назвала спрошенный сезон - несёт его."""
    named = replace(film("Моб Психо 100 [S01] BDRip", kind="tv"), season=1)
    picture = Picture(title="Моб Психо 100", year=2016, kind="tv", part=3, releases=[named])

    assert carries_season(picture, 1) is True


def test_a_mismatched_part_number_that_no_release_names_does_not_carry_the_season() -> None:
    """🔴 TC-860. Часть чужая, и ни одна раздача сезон не назвала - не несёт его.

    Ровно этот случай молчала честная строка выбора: дефолт садился на такую картину
    первым пунктом меню, и говорить было не о чем только на первый взгляд.
    """
    picture = Picture(title="Мираж 2", year=2018, kind="tv", part=2)

    assert carries_season(picture, 1) is False
