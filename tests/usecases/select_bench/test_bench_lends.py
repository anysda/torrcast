"""Стенд карточки не убирает раздачу, которую поиск дорожки срезал недочитанной."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator

import pytest

from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.release import Release
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
