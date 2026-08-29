"""Зеркало :mod:`torrcast.usecases.choice.asked_season_number`: сезон запроса, если он один.

Вынесен из :mod:`torrcast.usecases.choice.asked_season` под TC-860: тот же вопрос стал
нужен и честной строке выбора (:func:`~torrcast.usecases.choice.default_note.default_note`),
не только сужению меню.
"""

from __future__ import annotations

from tests.usecases.choice.world import plan
from torrcast.usecases.choice.asked_season_number import asked_season_number


def test_a_named_episode_gives_back_the_season_it_named() -> None:
    """Серию назвали - сезон один, и это он."""
    geass = [
        plan("Код Гиас: Восставший Лелуш 2", 2008, kind="tv", part=2, season=1, asked_series=True),
        plan("Код Гиас: Восставший Лелуш", 2006, kind="tv", season=1, asked_series=True),
    ]

    assert asked_season_number(geass) == 1


def test_no_episode_named_gives_no_season() -> None:
    """Серии не спрашивали - номер сезона не назван, и судить по нему нечем."""
    geass = [plan("Код Гиас: Восставший Лелуш", 2006, kind="tv")]

    assert asked_season_number(geass) is None


def test_disagreeing_plans_give_no_season() -> None:
    """Планы разошлись в сезоне - единого ответа нет, и он не выдумывается."""
    mixed = [
        plan("Раз", 2020, kind="tv", season=1, asked_series=True),
        plan("Два", 2021, kind="tv", season=2, asked_series=True),
    ]

    assert asked_season_number(mixed) is None
