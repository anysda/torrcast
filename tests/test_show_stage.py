"""Показ с карточки берёт круг карточки, а не заводит второй рядом."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import web.show_stage as show_stage
from tests.test_warm_cache import _TOLD
from tests.usecases.cast_command.world import GB, plans
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.release import Release
from torrcast.usecases.discover.told_circle import ToldCircle
from torrcast.usecases.select.plan import Plan
from web.circle_disk import CircleDisk
from web.warm_cache import WarmCache


class _Warm:
    def __init__(self, circle: list[Any]) -> None:
        self.circle, self.asked = circle, []  # type: list[Any], list[str]

    def take_live(self, query: str) -> list[Any]:
        self.asked.append(query)
        return self.circle

    def landed(self, query: str) -> list[Any] | None:
        return None


class _Late:
    def __init__(self) -> None:
        self.lock = threading.Lock()

    def drain(self) -> list[Any]:
        return []


def _search(*_rest: object) -> list[Any]:
    raise AssertionError("второй круг рядом с кругом карточки")


def test_a_card_show_takes_the_card_circle_as_a_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    warm = _Warm(plans(2))
    monkeypatch.setattr(show_stage, "WARM", warm)
    monkeypatch.setattr(show_stage, "search_circle", _search)

    got = show_stage._card_circle(Any, Args(query=["тачки"], picture="k"), Any, Any)  # type: ignore[arg-type]

    assert warm.asked == ["тачки"]
    assert [p.picture.key for p in got] == [p.picture.key for p in warm.circle]
    assert got[0] is not warm.circle[0], "отбор переставляет планы, кэш карточки служит дальше"


def test_the_card_circle_copies_plans_whose_late_answer_holds_a_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Живой круг держит опоздавший индексер замыканием с замком: глубокая копия падала."""
    circle = plans(1)
    circle[0].late = _Late().drain
    monkeypatch.setattr(show_stage, "WARM", _Warm(circle))

    got = show_stage._card_circle(Any, Args(query=["тачки"], picture="k"), Any, Any)  # type: ignore[arg-type]
    got[0].picture.kind = "tv"
    got[0].ranked.clear()

    assert circle[0].picture.kind != "tv" and circle[0].ranked, "кэш карточки не тронут"
    assert got[0].late is circle[0].late


def test_a_show_without_the_card_key_searches_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    """Консоль и Home Assistant карточки не называют; серия без согретого круга ищет сама."""
    warm, own = _Warm(plans(2)), plans(1)
    monkeypatch.setattr(show_stage, "WARM", warm)
    monkeypatch.setattr(show_stage, "search_circle", lambda *_rest: own)

    for asked in (Args(query=["тачки"]), Args(query=["шоу", "s1e2"], picture="k")):
        assert show_stage._card_circle(Any, asked, Any, Any) is own  # type: ignore[arg-type]
    assert warm.asked == []


def test_the_card_picture_is_found_by_the_card_rule() -> None:
    menu = plans(3)

    assert show_stage._card_picture(menu, menu[2].picture.key) == 3
    assert show_stage._card_picture(menu, "movie:никто:1900") == 0


class _CardWarm:
    def __init__(self) -> None:
        self.taken: list[tuple[str, object]] = []

    def take(self, key: str, fresh: object) -> str:
        self.taken.append((key, fresh))
        return "стенд карточки"


def test_a_card_show_asks_the_card_warm_for_its_bench(monkeypatch: pytest.MonkeyPatch) -> None:
    """Картину без серии карточка уже греет; серия и консоль отбирают своим стендом."""
    warm = _CardWarm()
    monkeypatch.setattr(show_stage, "CARD_WARM", warm)

    assert show_stage._card_bench(Args(query=["тачки"], picture="k"), "свой") == "стенд карточки"  # type: ignore[arg-type,comparison-overlap]
    for asked in (Args(query=["тачки"]), Args(query=["шоу", "s1e2"], picture="k")):
        assert show_stage._card_bench(asked, "свой") == "свой"  # type: ignore[arg-type,comparison-overlap]
    assert warm.taken == [("k", "свой")]


def _season(number: int, magnet: str) -> Release:
    return Release(
        raw_name=f"Шоу / Show / Сезон: {number} / Серии: 1-10 (2013) WEB-DL 1080p",
        title="Шоу",
        year=2013,
        kind="tv",
        season=number,
        quality="1080p",
        codec="H.264",
        voices=("Дубляж",),
        size=8 * GB,
        seeders=100,
        magnet=magnet,
    )


class _Ready(_Warm):
    def landed(self, query: str) -> list[Any] | None:
        self.asked.append(query)
        return self.circle


def _show_circle(*releases: Release) -> list[Plan]:
    picture = Picture(title="Шоу", year=2013, kind="tv", releases=list(releases))
    card = Plan(picture=picture, ranked=[releases[0]], runtime=1500.0, warn_mbit=16.0)
    return [card]


def test_an_episode_row_takes_the_warm_card_circle_ranked_for_its_season(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Строка серии не ищет второй раз: круг карточки перекладывается под сезон строки.

    Живой замер «Рик и Морти» s2e1: свой поиск показа стоил 5 с, а выдача та же.
    """
    circle = _show_circle(_season(1, "magnet:one"), _season(2, "magnet:two"))
    warm = _Ready(circle)
    monkeypatch.setattr(show_stage, "WARM", warm)
    monkeypatch.setattr(show_stage, "search_circle", _search)
    asked = Args(query=["шоу", "s2e1"], picture=circle[0].picture.key)

    got = show_stage._card_circle(Config(), asked, Any, CAUTIOUS)  # type: ignore[arg-type]

    assert warm.asked == ["шоу"]
    assert [r.magnet for r in got[0].ranked] == ["magnet:two"]
    assert got[0].series is not None and got[0].series.want == Episode(2, 1)
    assert [r.magnet for r in circle[0].ranked] == ["magnet:one"], "кэш карточки не тронут"


def test_a_card_circle_without_the_asked_season_leaves_the_reinforce_to_the_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    own = plans(1)
    monkeypatch.setattr(show_stage, "WARM", _Ready(_show_circle(_season(1, "magnet:one"))))
    monkeypatch.setattr(show_stage, "search_circle", lambda *_rest: own)
    asked = Args(query=["шоу", "s3e1"], picture="tv:шоу:2013")

    assert show_stage._card_circle(Config(), asked, Any, CAUTIOUS) is own  # type: ignore[arg-type]


def test_an_episode_row_does_not_play_a_card_circle_revived_from_disk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """🔴 Строка s2e1 играла круг с диска двухчасовой давности: 0 стартов из 4 на стенде."""
    circle = _show_circle(_season(1, "magnet:one"), _season(2, "magnet:two"))
    disk = CircleDisk(path=lambda: tmp_path / "circles.json")

    def _warm(spawn: Callable[[Callable[[], None]], None]) -> WarmCache:
        told = ToldCircle(circle, _TOLD)
        return WarmCache(
            lambda _q: told, lambda _p: None, spawn, disk=disk, replay=lambda *_: circle
        )

    _warm(lambda job: job()).take("шоу")
    warm = _warm(lambda job: job())
    warm.ask(["шоу"])
    assert warm.ready("шоу") is not None, "карточка круг с диска показывает"
    own = plans(1)
    monkeypatch.setattr(show_stage, "WARM", warm)
    monkeypatch.setattr(show_stage, "search_circle", lambda *_rest: own)
    asked = Args(query=["шоу", "s2e1"], picture=circle[0].picture.key)

    assert show_stage._card_circle(Config(), asked, Any, CAUTIOUS) is own  # type: ignore[arg-type]
