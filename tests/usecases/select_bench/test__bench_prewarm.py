"""Зеркало прогрева под меню: переезд номеров, уборка чужих картин и запасной релиз."""

from __future__ import annotations

from dataclasses import replace

from tests.usecases.select_bench.world import Torrents, plan, probes, rel
from torrcast.cli.args import Args
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select._plan import _Plan
from torrcast.usecases.select_bench._bench import _Bench

_ASKED = Args(query=["кино"])


def _ranked(count: int, dubbed: bool = True) -> list[Release]:
    tail = " | Дубляж" if dubbed else ""
    return [rel(name=f"r{n}{tail}", seeders=100 - n) for n in range(count)]


def test_the_warmed_release_moves_with_its_number_not_with_the_digit() -> None:
    """Переезд считается по самой раздаче: та же цифра после пересборки - другой магнит."""
    pool = _ranked(2)
    before = plan(pool)
    bench = _Bench(Torrents(), prober=probes([]))
    warmed = bench.start(before, 1)
    after = plan(list(reversed(pool)))

    assert bench.reorder(before, after) is after
    assert warmed.number == 2, "раздача уехала вниз - вместе с ней уехал и её прогрев"
    assert bench.preps[(after.picture.key, 2)] is warmed


def test_a_release_that_fell_out_of_the_order_loses_its_warm_up() -> None:
    """Раздачи в новом порядке нет вовсе - прогрев отпускается, а не переносится наугад."""
    pool = _ranked(2)
    before = plan(pool)
    torrents = Torrents()
    bench = _Bench(torrents, prober=probes([]))
    warmed = bench.start(before, 2)
    warmed.ready.wait(2.0)

    bench.reorder(before, plan(pool[:1]))

    assert warmed.dropped is True


def test_the_chosen_picture_leaves_no_warm_ups_of_the_neighbours() -> None:
    """Картина выбрана - чужие прогревы доедали бы полосу у той, что вот-вот покажем."""
    mine = plan(_ranked(1))
    other = _Plan(
        picture=Picture(title="Другое", year=2001, releases=_ranked(1)),
        ranked=_ranked(1),
        runtime=3600.0,
        warn_mbit=20.0,
    )
    bench = _Bench(Torrents(), prober=probes([]))
    kept = bench.start(mine, 1)
    dropped = bench.start(other, 1)
    for prep in (kept, dropped):
        prep.ready.wait(2.0)

    bench.keep_plan(mine)

    assert (kept.dropped, dropped.dropped) == (False, True)


def test_the_spare_release_is_the_next_one_the_queue_would_take() -> None:
    """Очередь та же, что спросит отбор, и следующий в ней - тот, кого он поднимет первым."""
    built = plan(_ranked(3))
    bench = _Bench(Torrents(), prober=probes([]))

    preps = bench.spare(built, _ASKED)

    assert [prep.number for prep in preps] == [2]


def test_a_release_named_by_hand_has_no_spare_at_all() -> None:
    """Очередь из одного номера - подменять человека нечем, и лишней раздачи не будет."""
    bench = _Bench(Torrents(), prober=probes([]))

    assert bench.spare(plan(_ranked(3)), Args(query=["кино"], release=1)) == []


def test_a_silent_top_warms_the_first_release_that_promises_russian() -> None:
    """🔴 TC-309. Гейт уведёт очередь к обещавшей русскую - её и греем заодно."""
    pool = [
        replace(rel(name="r0", seeders=100), raw_name="r0"),
        replace(rel(name="r1", seeders=90), raw_name="r1"),
        replace(rel(name="r2 | Дубляж", seeders=80), raw_name="r2 | Дубляж"),
    ]
    bench = _Bench(Torrents(), prober=probes([]))

    preps = bench.spare(plan(pool), _ASKED)

    assert sorted(prep.number for prep in preps) == [2, 3]
