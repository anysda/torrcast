"""Зеркало вопроса о годности пула: есть ли во всей выдаче раздача, которой стоит играть."""

from __future__ import annotations

from tests.usecases.discover.world import franchise, row
from torrcast.adapters.prowlarr.raw_result import RawResult
from torrcast.cli.args import Args
from torrcast.domain.config import Config
from torrcast.usecases.discover.unfit_pool import unfit_pool

#: Живой годный 1080p: этой картиной вечер состоится.
_GOOD = row("Тачки / Cars (2006) BDRip 1080p | D", "a", size_gb=5.0, seeders=66)
#: Старьё: DVDRip играется, когда другого нет вовсе, но вечера он не обещает.
_DATED = row("Тачки / Cars (2006) DVDRip", "b", size_gb=1.4, seeders=40)
#: Мертвец: годен по имени, но сидов у него нет.
_DEAD = row("Тачки / Cars (2006) BDRip 1080p", "c", size_gb=5.0, seeders=0)


def _unfit(rows: list[RawResult]) -> bool:
    return unfit_pool(franchise("тачки", rows), Args(query=["тачки"]), Config())


def test_a_pool_with_a_living_release_is_fit() -> None:
    """Годная, живая и не старьё - вечер по этой выдаче состоится."""
    assert _unfit([_GOOD, _DATED, _DEAD]) is False


def test_a_pool_of_nothing_but_old_and_dead_is_unfit() -> None:
    """🔴 TC-245. Раздач много, а играть нечем - толщина пула о годности молчит."""
    assert _unfit([_DATED, _DEAD]) is True


def test_an_empty_find_is_unfit_too() -> None:
    """Картины нет вовсе - годного в ней тем более."""
    assert _unfit([]) is True
