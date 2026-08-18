"""Зеркало ядра стенда: заведённые прогревы, место под них и уборка за собой."""

from __future__ import annotations

from tests.usecases.select_bench.world import Torrents, plan, probes, rel
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench._bench import _Bench


def _bench(torrents: Torrents) -> _Bench:
    return _Bench(torrents, prober=probes([]))


def test_a_prep_that_is_no_longer_needed_is_dropped_by_its_own_hash() -> None:
    """Раздача убирается по СВОЕМУ хэшу: в списке службы лежат и чужие."""
    torrents = Torrents()
    bench = _bench(torrents)
    prep = _Prep(number=1, release=rel(), torrent_hash="hash-мой")

    bench._forget(prep)

    assert torrents.dropped == ["hash-мой"]
    assert prep.dropped is True


def test_the_live_preps_are_the_ones_still_standing_in_the_service() -> None:
    """Живой прогрев - тот, за которым в службе стоит (или встанет) наша раздача."""
    torrents = Torrents()
    bench = _bench(torrents)
    built = plan([rel(name=f"r{n}", seeders=100 - n) for n in range(2)])

    first = bench.start(built, 1)
    second = bench.start(built, 2)
    bench._forget(first)

    assert bench.live() == [second]


def test_starting_the_same_release_twice_gives_back_the_same_preparation() -> None:
    """Второй раз греть то же самое незачем: прогрев на релиз один."""
    bench = _bench(Torrents())
    built = plan([rel()])

    assert bench.start(built, 1) is bench.start(built, 1)


def test_the_show_is_not_going_and_everything_warmed_is_taken_away() -> None:
    """Выходов мимо отбора хватает - и прогретое не остаётся тянуть кэш чужой службы."""
    torrents = Torrents()
    bench = _bench(torrents)
    built = plan([rel(name=f"r{n}", seeders=100 - n) for n in range(2)])
    for prep in (bench.start(built, 1), bench.start(built, 2)):
        prep.ready.wait(2.0)

    bench.drop_all()

    assert len(torrents.dropped) == 2
    assert bench.live() == []


def test_only_the_chosen_release_survives_the_start_of_the_show() -> None:
    """Прогрев греет лишнее по определению, и лишнее обязано исчезнуть до старта."""
    torrents = Torrents()
    bench = _bench(torrents)
    built = plan([rel(name=f"r{n}", seeders=100 - n) for n in range(2)])
    chosen = bench.start(built, 1)
    other = bench.start(built, 2)
    for prep in (chosen, other):
        prep.ready.wait(2.0)

    bench.keep_only(chosen)

    assert bench.live() == [chosen]
