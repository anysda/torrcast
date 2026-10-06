"""Зеркало :mod:`torrcast.usecases.choice.renowned_work`: версии самой известной работы."""

from __future__ import annotations

from tests.usecases.choice.world import parts
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.usecases.choice.renowned_work import renowned_work
from torrcast.usecases.discover._search_state import _configure_known

MUMMY = parts(("Мумия", 1999, 65), ("Мумия", 2017, 29), ("Мумия", 2026, 826))


def test_the_versions_of_the_best_known_work_stay() -> None:
    """«мумия»: 1999 и 2017 - одна работа «The Mummy», 2026 - другая и менее известная."""
    known = [
        MapPicture("Мумия", 1999, False, "The Mummy", 509911),
        MapPicture("Мумия", 2017, False, "The Mummy", 225639),
        MapPicture("Мумия", 2026, False, "Lee Cronin's the Mummy", 74476),
    ]
    _configure_known(lambda title: [row for row in known if row.name == title])

    assert renowned_work(MUMMY, [1, 2, 3]) == [1, 2]


def test_a_silent_map_keeps_every_namesake() -> None:
    _configure_known(lambda _title: [])

    assert renowned_work(MUMMY, [1, 2, 3]) == [1, 2, 3]
