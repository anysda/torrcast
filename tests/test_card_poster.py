"""CardPoster: имя обложки карточки только после приговора, один поход в сеть на картину."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from torrcast.domain.server_down_error import ServerDownError
from web.card_poster import CardPoster

#: Имя из замера на стенде: плитка звала картину «GARO», круг карточки - «Garo».
_GARO = Picture(title="Usuzumizakura Garo", year=2018, kind="tv", original="Usuzumizakura GARO")


class _Verdict:
    """Приговор-счётчик: помнит, о чём спрашивали, и ставит имя, если оно задано."""

    def __init__(self, name: str | None = None, fails: bool = False) -> None:
        self.name = name
        self.fails = fails
        self.asked: list[JsonValue] = []

    def __call__(self, records: list[JsonValue]) -> list[JsonValue]:
        self.asked.extend(records)
        if self.fails:
            raise ServerDownError("posters_down")
        if self.name is None:
            return records
        return [{**record, "poster": self.name} for record in records if isinstance(record, dict)]


def _sync(job: Callable[[], None]) -> None:
    job()


def test_the_card_names_a_poster_only_once_the_verdict_found_the_picture() -> None:
    verdict = _Verdict("f00d")
    poster = CardPoster(offer=verdict, spawn=_sync)

    assert poster.of(_GARO) == ("f00d", False)
    assert verdict.asked == [
        {
            "title": "Usuzumizakura Garo",
            "year": 2018,
            "kind": "tv",
            "original": "Usuzumizakura GARO",
        }
    ]


def test_a_miss_is_remembered_so_the_next_open_does_not_ask_the_network_again() -> None:
    now = [0.0]
    verdict = _Verdict()
    poster = CardPoster(offer=verdict, spawn=_sync, clock=lambda: now[0])

    assert poster.of(_GARO) == (None, False)
    assert poster.of(_GARO) == (None, False)
    assert len(verdict.asked) == 1

    now[0] = 601.0
    poster.of(_GARO)
    assert len(verdict.asked) == 2, "промах держится сроком, а не вечно"


def test_while_the_verdict_is_on_its_way_the_card_says_ask_again_and_asks_once() -> None:
    jobs: list[Callable[[], None]] = []
    poster = CardPoster(offer=_Verdict("f00d"), spawn=jobs.append)

    assert poster.of(_GARO) == (None, True)
    assert poster.of(_GARO) == (None, True)
    assert len(jobs) == 1, "второй заход карточки второго приговора не заводит"

    jobs[0]()
    assert poster.of(_GARO) == ("f00d", False)


def test_a_failed_verdict_is_a_miss_not_a_dead_background_thread() -> None:
    poster = CardPoster(offer=_Verdict(fails=True), spawn=_sync)

    assert poster.of(_GARO) == (None, False)
