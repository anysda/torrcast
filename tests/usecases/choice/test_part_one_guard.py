"""Зеркало :mod:`torrcast.usecases.choice.part_one_guard`: причина стража без готовой фразы.

Одну причину читают две строки: меню («назови номер») и взятие без ``--menu`` («беру
первую живую»). Поэтому страж отдаёт ключ и поля, а фразу собирает тот, кто говорит.
"""

from __future__ import annotations

from tests.usecases.choice.world import plan
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice.part_one_guard import part_one_guard


def test_a_dead_first_part_names_its_key_and_reason() -> None:
    cars = [plan("Тачки", 2006, part=1, seeders=2), plan("Тачки 2", 2011, part=2, seeders=40)]

    assert part_one_guard(cars, "тачки") == (
        "choice.part_one_dead_why",
        {"picture": "Тачки (2006)", "why": phrase("choice.why_dead_swarm", seeds=2)},
    )


def test_a_missing_first_part_names_the_asked_franchise() -> None:
    cars = [plan("Тачки 2", 2011, part=2, seeders=40), plan("Тачки 3", 2017, part=3, seeders=121)]

    assert part_one_guard(cars, "тачки") == ("choice.part_one_absent", {"name": "тачки"})


def test_a_living_first_part_or_a_named_number_keeps_the_guard_silent() -> None:
    cars = [plan("Тачки", 2006, part=1, seeders=50), plan("Тачки 2", 2011, part=2, seeders=40)]

    assert part_one_guard(cars, "тачки") == ("", {})
    assert part_one_guard(cars, "тачки 2") == ("", {})
