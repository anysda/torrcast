"""Зеркало ядра стенда: заведённые прогревы, место под них и уборка за собой."""

from __future__ import annotations

from tests.usecases.select_bench.world import Torrents, plan, probes, rel
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench.bench import Bench
from torrcast.usecases.torrent_claims import CLAIMS


def _bench(torrents: Torrents) -> Bench:
    return Bench(torrents, prober=probes([]))


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


def test_a_release_another_holder_keeps_is_not_dropped_under_it() -> None:
    """🔴 Карточка страницы и отбор показа держат одну раздачу: уборка карточки её не сносит.

    Стенд 14-09-2026: «Тачки» с карточки упали на 404 - прогрев карточки ушёл со страницы
    и снёс раздачу, которую в ту же секунду отбирал показ.
    """
    torrents = Torrents()
    card, show = _bench(torrents), _bench(torrents)
    mine = _Prep(number=1, release=rel(), torrent_hash="hash-общий-карточки")
    CLAIMS.claim(mine.torrent_hash, card)
    CLAIMS.claim(mine.torrent_hash, show)

    card._forget(mine)
    assert torrents.dropped == [], "раздачу держит отбор показа"

    show._forget(_Prep(number=1, release=rel(), torrent_hash="hash-общий-карточки"))
    assert torrents.dropped == ["hash-общий-карточки"], "последний держатель убирает за собой"


def test_a_second_prep_of_the_chosen_torrent_does_not_drop_it_on_keep_only() -> None:
    """🔴 Показ с карточки завёл выбранную карточкой раздачу вторым прогревом стенда.

    Стенд 14-09-2026, «История игрушек»: ``keep_only`` убрал второй прогрев того же хэша и
    снёс выбранную раздачу, юнит добавил её заново и ждал файлы 7.9 с.
    """
    torrents = Torrents()
    bench = _bench(torrents)
    card = _Prep(number=1, release=rel(), torrent_hash="hash-выбранный")
    chosen = _Prep(number=1, release=rel(), torrent_hash="hash-выбранный")
    bench.preps = {("карточка", 1): card, ("показ", 1): chosen}
    CLAIMS.claim(chosen.torrent_hash, bench)

    bench.keep_only(chosen)
    assert torrents.dropped == [], "выбранная раздача стоит за живым прогревом"

    bench.drop_all()
    assert torrents.dropped == ["hash-выбранный"], "последний прогрев хэша убирает за собой"


def test_a_prep_dropped_while_it_warmed_lets_its_release_go() -> None:
    """Прогрев убрали, пока он грелся: его отметка снимается, и раздача уходит из службы."""
    torrents = Torrents()
    bench = _bench(torrents)
    prep = _Prep(number=1, release=rel(name="поздний"), dropped=True)

    bench._work(plan([rel(name="поздний")]), prep)

    assert prep.torrent_hash in torrents.dropped
    assert CLAIMS.claimed(prep.torrent_hash) is False
