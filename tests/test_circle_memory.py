"""Память кругов: находка на срок, отказ на минуту, пустое не находка."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from tests.test_warm_cache import _PLAN, _SHOWN, _sync
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover.cut_circle import CutCircle
from torrcast.usecases.discover.told_circle import ToldCircle
from torrcast.usecases.discover.told_indexer import Told
from torrcast.usecases.select.plan import Plan
from web.circle_disk import CircleDisk
from web.circle_memory import EMPTY_TTL, CircleMemory
from web.warm_cache import WarmCache


def test_a_refusal_lives_a_minute_and_a_later_find_replaces_it() -> None:
    """Отказ помнится минуту, свежая находка его снимает, пустая находка не пишется."""
    now = [0.0]
    memory = CircleMemory(clock=lambda: now[0], ttl=300.0)
    plan = cast(Any, object())

    memory.refuse(" Lost ", NotFoundError("nothing"))
    memory.keep("Lost", [])

    assert memory.plans("Lost") == []
    assert isinstance(memory.refusal("Lost"), NotFoundError)
    memory.keep("Lost", [plan])
    assert memory.plans("Lost ") == [plan]
    assert memory.refusal("Lost") is None
    now[0] += 301.0
    assert memory.plans("Lost") is None
    memory.refuse("Lost", NotFoundError("nothing"))
    now[0] += EMPTY_TTL + 1.0
    assert memory.plans("Lost") is None


def test_a_cut_circle_is_kept_a_minute_not_the_full_term() -> None:
    """🔴 Круг, где JacRed сдался, помнился пять минут как полный."""
    now = [0.0]
    memory = CircleMemory(clock=lambda: now[0], ttl=300.0)
    plan = cast(Any, object())

    memory.keep("Тачки", CutCircle([plan]))
    now[0] += EMPTY_TTL - 1.0
    assert memory.plans("Тачки") == [plan]
    now[0] += 2.0
    assert memory.plans("Тачки") is None


def test_a_slug_line_finds_the_network_circle_of_the_same_spelling() -> None:
    """История несёт «рататуй», круг согрет под «Рататуй»; чужое имя и дисковое не берутся."""
    now = [0.0]
    memory = CircleMemory(clock=lambda: now[0], ttl=300.0)
    plan, other = cast(Any, object()), cast(Any, object())

    memory.keep("Рататуй", [plan])
    memory.keep("Рататуй 2", [other])

    assert memory.alike("рататуй") == [plan]
    assert memory.live("рататуй") is None
    assert memory.alike("Тачки") is None
    now[0] += 301.0
    assert memory.alike("рататуй") is None


def test_a_circle_not_every_indexer_answered_lives_a_minute_and_gives_way_on_disk(
    tmp_path: Path,
) -> None:
    """🔴 «Начало» показывало 2 плитки вместо 20 в 30 заходах подряд: круг, где JacRed и
    RuTor смолчали, лёг на диск на сутки как полный и заслонял собой каждый следующий."""
    now = [0.0]
    told: list[Told] = [
        ("search", "Начало", 0.0, (), [RawResult("Начало", "a", indexer="AniLibria")])
    ]
    whole: list[Told] = [("search", "Начало", 0.0, (), [RawResult("Начало", "b", indexer="RuTor")])]
    answers = [ToldCircle([_PLAN], told), ToldCircle([_PLAN, _SHOWN], whole, whole=True)]
    asked: list[str] = []

    def circle(query: str) -> list[Plan]:
        asked.append(query)
        return answers[len(asked) - 1]

    disk = CircleDisk(path=lambda: tmp_path / "circles.json")
    cache = WarmCache(
        circle, lambda _p: None, _sync, clock=lambda: now[0], disk=disk, replay=lambda *_: [_PLAN]
    )

    assert cache.take("Начало") == [_PLAN]
    assert disk.part("Начало"), "the cut circle lies on disk only with its mark"
    now[0] += EMPTY_TTL - 1.0
    assert cache.take("Начало") == [_PLAN]
    assert asked == ["Начало"], "inside its minute the cut circle is not asked again"
    now[0] += 2.0
    cache.take("Начало")
    assert asked == ["Начало", "Начало"], "after it the network is asked behind the disk"
    assert (disk.told("Начало"), disk.part("Начало")) == (whole, False), (
        "the next circle takes the marked one's place, though AniLibria is not in it"
    )
    assert cache.take("Начало") == [_PLAN, _SHOWN]


def test_a_circle_only_prowlarr_cut_short_keeps_its_full_term_and_the_disk(
    tmp_path: Path,
) -> None:
    """🔴 With Knaben out of reach for hours no shelf circle reached the disk, and every home
    screen after a minute asked the network again: one Prowlarr took away was not asked."""
    now = [0.0]
    told: list[Told] = [("search", "Тачки", 0.0, (), [RawResult("Тачки", "a", indexer="RuTor")])]
    asked: list[str] = []

    def circle(query: str) -> list[Plan]:
        asked.append(query)
        return ToldCircle([_PLAN], told, whole=False, heard=True)

    disk = CircleDisk(path=lambda: tmp_path / "circles.json")
    cache = WarmCache(
        circle, lambda _p: None, _sync, clock=lambda: now[0], disk=disk, replay=lambda *_: [_PLAN]
    )

    assert cache.take("Тачки") == [_PLAN]
    assert disk.told("Тачки") == told, "the circle goes to disk for its day"
    now[0] += EMPTY_TTL + 1.0
    assert cache.take("Тачки") == [_PLAN]
    assert asked == ["Тачки"], "after a minute the circle is still the memory's answer"


def test_a_cut_circle_as_rich_as_the_whole_one_on_disk_stands_for_it(tmp_path: Path) -> None:
    """Not poorer than the kept whole circle, a cut one replaces it and keeps its guard."""
    rows = [RawResult("Тачки", "a", indexer="RuTor"), RawResult("Тачки", "b", indexer="YTS")]
    whole: list[Told] = [("search", "Тачки", 0.0, (), rows)]
    richer: list[Told] = [("search", "Тачки", 0.0, (), [*rows, RawResult("Тачки 2", "c")])]
    poorer: list[Told] = [("search", "Тачки", 0.0, (), rows[:1])]
    disk = CircleDisk(path=lambda: tmp_path / "circles.json")
    memory = CircleMemory(clock=lambda: 0.0, ttl=300.0, disk=disk)
    disk.keep("Тачки", whole)

    memory.store("Тачки", ToldCircle([_PLAN], richer))
    assert (disk.told("Тачки"), disk.part("Тачки")) == (richer, False)
    memory.store("Тачки", ToldCircle([_PLAN], poorer))
    assert disk.told("Тачки") == richer, "a cut circle without YTS does not replace it"
