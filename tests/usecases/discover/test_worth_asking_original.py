"""Зеркало повода переспросить оригиналом: тощий пул и негодный пул - поводы разные."""

from __future__ import annotations

from tests.usecases.discover.world import franchise, row
from torrcast.adapters.prowlarr.raw_result import RawResult
from torrcast.cli.args import Args
from torrcast.domain._name_data import THIN_POOL
from torrcast.domain.config import Config
from torrcast.usecases.discover.worth_asking_original import worth_asking_original


def _worth(rows: list[RawResult], query: str = "психо") -> bool:
    return worth_asking_original(franchise(query, rows), Args(query=[query]), Config())


def _fat(count: int, *, seeders: int = 60, quality: str = "BDRip 1080p") -> list[RawResult]:
    return [
        row(f"Психо / Psycho (1960) {quality} {n}", chr(97 + n % 26) + str(n), seeders=seeders)
        for n in range(count)
    ]


def test_a_thin_pool_is_a_reason_by_itself() -> None:
    """Строк меньше порога - русской выдачи не хватило, и второе имя стоит круга."""
    assert _worth(_fat(2)) is True


def test_a_fat_and_fit_pool_pays_for_no_second_circle() -> None:
    """Годная раздача есть и пул толст - второго захода нет: круг не бесплатный."""
    assert _worth(_fat(THIN_POOL + 1)) is False


def test_a_fat_but_unfit_pool_is_the_second_reason() -> None:
    """🔴 TC-245. Строк много, а играть нечем - толщина о годности не говорит ничего."""
    assert _worth(_fat(THIN_POOL + 1, quality="DVDRip")) is True
