"""Стенд карточки не убирает раздачу, которую поиск дорожки срезал недочитанной."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator

import pytest

from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.release import Release
from torrcast.domain.swarm_error import SwarmError
from torrcast.usecases.select_bench.bench import Bench


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Обход печатает русские строки."""


@pytest.fixture
def slow() -> Iterator[threading.Event]:
    """Паспорт второй раздачи читается, пока тест его не отпустит."""
    gate = threading.Event()
    yield gate
    gate.set()


def _prober(pool: list[Release], slow: threading.Event) -> Callable[..., Media]:
    """Первая раздача сразу называет японский звук, вторая ещё читается."""
    japanese = Media(RUNTIME, (AudioTrack(index=0, language="jpn"),), "h264", height=1080)

    def read(
        source_url: str, /, timeout: float = 90.0, alive: Callable[[], bool] | None = None
    ) -> Media:
        if f"hash-{pool[1].magnet}/" in source_url:
            slow.wait(5.0)
            return Media(RUNTIME, (AudioTrack(index=0, language="rus"),), "h264", height=1080)
        return japanese

    return read


def _resolved(lends: bool, slow: threading.Event) -> tuple[Bench, Torrents, str]:
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(2)]
    torrents = Torrents()
    bench = Bench(torrents, prober=_prober(pool, slow), voice_budget=0.3, lends=lends)
    prep = bench.resolve(plan(pool), Args(query=["кино"]), Said())
    assert prep.number == 1, "срок поиска дорожки кончился: играет запасной ход"
    bench.keep_only(prep)
    return bench, torrents, f"hash-{pool[1].magnet}"


def test_the_card_keeps_reading_the_release_the_voice_hunt_cut(slow: threading.Event) -> None:
    """«Призрак в доспехах»: пока карточка на экране, №3 дочитывается, а не уходит из
    TorrServer, и показ после клика берёт его готовым, а не заводит заново."""
    bench, torrents, second = _resolved(True, slow)

    assert second not in torrents.dropped
    assert not bench.preps[("movie:кино:1999", 2)].dropped

    bench.lends = False  # стенд забрал показ: лишнее уходит по-прежнему
    bench.keep_only(bench.preps[("movie:кино:1999", 1)])
    assert second in torrents.dropped


def test_the_show_still_lets_the_cut_release_go(slow: threading.Event) -> None:
    """Показу ждать некого: срезанная сроком раздача убирается сразу."""
    _bench, torrents, second = _resolved(False, slow)

    assert second in torrents.dropped


def _refused(lends: bool, slow: threading.Event) -> tuple[Bench, Torrents, str]:
    """№1 молчит, №2 назвал японский звук, №3 не дочитан к сроку: отбор отказывает."""
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(4)]
    japanese = Media(RUNTIME, (AudioTrack(index=0, language="jpn"),), "h264", height=1080)

    def read(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        if f"hash-{pool[0].magnet}/" in source_url:
            raise SwarmError("рой молчит", waited=20.0)
        if f"hash-{pool[2].magnet}/" in source_url:
            slow.wait(5.0)
        return japanese

    torrents = Torrents()
    bench = Bench(torrents, prober=read, pick_budget=0.6, lends=lends)
    with pytest.raises(NotFoundError):
        bench.resolve(plan(pool), Args(query=["кино"]), Said())
    return bench, torrents, f"hash-{pool[1].magnet}"


def test_the_card_keeps_the_release_whose_voice_it_already_read(slow: threading.Event) -> None:
    """«Призрак в доспехах»: карточка узнала японский звук №2, и показ не читает его заново 3 с."""
    bench, torrents, second = _refused(True, slow)

    assert second not in torrents.dropped
    assert not bench.preps[("movie:кино:1999", 2)].dropped


def test_the_show_lets_the_read_foreign_release_go(slow: threading.Event) -> None:
    """Показу этот запасной ход больше не нужен: раздача уходит сразу."""
    _bench, torrents, second = _refused(False, slow)

    assert second in torrents.dropped


def test_a_bench_warms_the_file_from_the_place_the_show_resumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Прогрев стенда тянет место закладки, а не начало файла; без закладки - начало."""
    from tests.fakes import composition

    places: list[object] = []

    def warm(_source: str, **kwargs: object) -> None:
        places.append(kwargs.get("at"))

    composition.use_warm_file(monkeypatch, warm)
    russian = Media(RUNTIME, (AudioTrack(index=0, language="rus"),), "h264", height=1080)
    pool = [rel(name="r | Дубляж", seeders=100)]
    for resume in (395.0, 0.0):
        bench = Bench(Torrents(), prober=lambda *_a, **_k: russian)
        bench.resume = resume
        bench.resolve(plan(pool), Args(query=["кино"]), Said())
    assert places == [395.0, 0.0]
