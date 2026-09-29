"""Зависший хост картинок одного источника не оставляет плитку без обложки и не зовёт API снова."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field

from hass.both_posters import BothPosters
from tests.test_both_posters import IMDB, PICTURE, THERE, WIKI, FakeSource
from torrcast.domain.facts.ask import Ask

IMDB_FULL = "https://m.media-amazon.com/images/M/one._V1_.jpg"


@dataclass
class StalledAmazon:
    """Загрузчик, у которого хост IMDb обрывает чтение на каждом файле."""

    asked: list[str] = field(default_factory=list)

    def fetch(self, address: str, timeout: float) -> bytes:
        self.asked.append(address)
        if "media-amazon" in address:
            raise TimeoutError("The read operation timed out")
        return PICTURE


@dataclass
class HeldWiki(FakeSource):
    """Википедия, чей ответ задержан: гонку ряда выигрывает IMDb."""

    gate: threading.Event = field(default_factory=threading.Event)

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        self.gate.wait(timeout)
        return super().wanted(asks, timeout)


def _raced(first: FakeSource, second: FakeSource, files: StalledAmazon) -> BothPosters:
    return BothPosters(first, second, files, urgent=True)


def test_a_stalled_imdb_host_hands_the_tile_to_the_loser_wikipedia_poster() -> None:
    """IMDb won the race, its host is silent: the tile takes Wikipedia's answer from that race.

    Wikipedia is still on the wire when the bytes fail; the spare waits for it in memory.
    """
    files, first = StalledAmazon(), HeldWiki({THERE: [WIKI]})
    second = FakeSource({THERE: [IMDB, IMDB_FULL]})
    both = _raced(first, second, files)
    wanted = both.wanted([THERE], 5.0)
    assert wanted == {THERE: [IMDB, IMDB_FULL]}
    threading.Timer(0.2, first.gate.set).start()
    assert both.bodies(wanted, 5.0) == {THERE: PICTURE}
    assert files.asked == [IMDB, IMDB_FULL, WIKI]


def test_a_bytes_miss_asks_no_source_api_again() -> None:
    """🔴 Ten tiles lose every IMDb file: each source was asked once, by the race, never after."""
    files, first = StalledAmazon(), HeldWiki()
    asks = [Ask(f"Film {n}", 2000 + n, "movie", f"Film {n}") for n in range(10)]
    first.known = {ask: [f"{WIKI}?{n}"] for n, ask in enumerate(asks)}
    second = FakeSource({ask: [f"{IMDB}?{n}"] for n, ask in enumerate(asks)})
    both = _raced(first, second, files)
    wanted = both.wanted(asks, 5.0)
    first.gate.set()
    got = both.bodies(wanted, 5.0)
    assert len(got) == 10, "a tile stayed bare although Wikipedia named its poster"
    assert first.asked == [asks] and second.asked == [asks], "the spare paid the API again"
    assert len(files.asked) == 20


def test_the_spare_walk_never_fetches_an_address_twice() -> None:
    """Нового адреса нет ни у кого - плитка остаётся без байт, и зависший хост не зовётся снова."""
    files, first, second = StalledAmazon(), FakeSource(), FakeSource({THERE: [IMDB]})
    both = _raced(first, second, files)
    wanted = both.wanted([THERE], 5.0)
    assert both.bodies(wanted, 5.0) == {}
    assert files.asked == [IMDB]
    assert first.asked == second.asked == [[THERE]]


def test_a_calm_row_has_no_race_to_spare_from_and_asks_nobody() -> None:
    """Спокойный путь второй источник об удачах первого не спрашивал: запаса нет, запроса нет."""
    first, second = FakeSource({THERE: [WIKI]}), FakeSource({THERE: [IMDB]})
    both = BothPosters(first, second, StalledAmazon())
    assert both.bodies({THERE: [IMDB]}, 5.0) == {}
    assert first.asked == second.asked == []
