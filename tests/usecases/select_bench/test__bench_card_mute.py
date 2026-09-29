"""Запасной ход карточки: показ, забравший её стенд, очередь заново не обходит."""

from __future__ import annotations

import time

import pytest

from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.usecases.select_bench.bench import Bench


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - запасной ход русской ручки: чужой звук, когда русского нет ни у кого."""


_ASKED = Args(query=["кино"])
_JPN = Media(RUNTIME, (AudioTrack(index=0, language="jpn"),), "h264", height=1080, width=1920)
_POOL = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(3)]


@pytest.mark.machine
def test_the_show_takes_the_card_mute_on_a_recounted_circle_without_a_second_walk() -> None:
    """🔴 «Призрак в доспехах» s1e1: круг пересчитан, а показ играет японский выбор карточки.

    Показ обошёл очередь второй раз по кругу, куда опоздавший индексер
    добавил раздач, и вместо японского №2 карточки взял немую 384p без кадра.
    """
    asked: list[str] = []
    read = probes(_POOL, _JPN, _JPN, _JPN)

    def prober(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        asked.append(source_url)
        return read(source_url, timeout=timeout)

    bench = Bench(Torrents(), prober=prober)
    card = bench.resolve(plan(_POOL), _ASKED, Said())
    assert card.voice_fallback, "карточка кончила запасным ходом"
    card.card_warmed = True  # так её оставляет прогрев карточки
    asked.clear()
    newcomer = rel(name="new | Дубляж", seeders=500)
    began = time.monotonic()

    prep = bench.resolve(plan([newcomer, *_POOL]), _ASKED, Said())

    assert prep is card
    assert prep.number == _POOL.index(card.release) + 2
    assert asked == [], "очередь второй раз не спрашивается"
    assert time.monotonic() - began < 0.5


@pytest.mark.machine
def test_a_card_that_found_its_voice_leaves_the_show_its_own_walk() -> None:
    """Без запасного хода карточки показ судит очередь сам, как прежде."""
    bench = Bench(Torrents(), prober=probes(_POOL, _JPN, _JPN, _JPN))
    card = bench.resolve(plan(_POOL), _ASKED, Said())
    card.card_warmed, card.voice_fallback = True, False

    prep = bench.resolve(plan(_POOL), _ASKED, Said())

    assert prep.voice_fallback, "показ сам дошёл до запасного хода"


@pytest.mark.machine
def test_a_release_the_card_read_keeps_its_passport_on_a_recounted_circle() -> None:
    """Прочитанное карточкой переезжает на новый номер, а не читается второй раз."""
    rus = Media(RUNTIME, (AudioTrack(index=0, language="rus"),), "h264", height=1080, width=1920)
    asked: list[str] = []
    newcomer = rel(name="new | Дубляж", seeders=99)
    read = probes([*_POOL, newcomer], _JPN, rus, rus, _JPN)

    def prober(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        asked.append(source_url)
        return read(source_url, timeout=timeout)

    bench = Bench(Torrents(), prober=prober)
    card = bench.resolve(plan(_POOL), _ASKED, Said())
    assert card.release is _POOL[1]

    prep = bench.resolve(plan([_POOL[0], newcomer, *_POOL[1:]]), _ASKED, Said())

    assert (prep.release, prep.number) == (_POOL[1], 3)
    assert sum(f"hash-{_POOL[1].magnet}/" in url for url in asked) == 1
