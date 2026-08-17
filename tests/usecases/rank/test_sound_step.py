"""Ступень звука по имени раздачи: русская обещана или нет."""

from __future__ import annotations

from tests.usecases.rank.releases import rel
from torrcast.usecases.rank.sound_step import sound_step

DUB = "Кино / Movie (1999) BDRip 1080p | Дубляж"
JAP = "Кино / Movie (1999) BDRip 1080p [JAP+Sub]"


def test_a_promised_russian_track_stands_a_step_higher() -> None:
    """У «Боруто» русский держит 3 сида против 8 у японского, и смотреть надо первый."""
    assert sound_step(rel(name=DUB), alive=100) == 0
    assert sound_step(rel(name=JAP), alive=100) == 1


def test_a_dead_swarm_is_no_win_in_any_language() -> None:
    """Без этого ступень поднимала раздачу с нулём сидов над играбельной."""
    dubbed = rel(name=DUB, seeders=5)
    assert sound_step(dubbed, alive=100) == 1


def test_an_unnamed_pool_leaves_the_clean_signal_of_the_name() -> None:
    """Ноль читается как «пул не назван»: так ступень зовут таблица релизов и тесты."""
    assert sound_step(rel(name=DUB, seeders=5)) == 0
