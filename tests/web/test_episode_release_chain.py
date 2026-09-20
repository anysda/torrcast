"""Строка серии играет ту раздачу, чьи файлы дали её вкладке, на всём пути до показа.

Звенья: ответ карточки (:mod:`web.card`), строка серии страницы (`card-series.js` и
`card.js`), ``argv`` показа (:func:`hass.play_argv.play_argv`) и круг показа с карточки
(:mod:`web.show_stage`). JavaScript-рантайма в гейте нет, поэтому звено страницы держит
договор текстом, как ``tests/test_home_search_poll.py``.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import web.card as card_page
import web.show_stage as show_stage
from hass.play_argv import play_argv
from tests.fakes.state_store import FakeStateStore
from tests.usecases.playback.world import FakeProgress
from torrcast.cli.parse_args import parse_args
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.facts.fact import Fact
from torrcast.domain.info_hash import info_hash
from torrcast.domain.picture import Picture
from torrcast.domain.profile import PROFILES, Profile
from torrcast.domain.release import Release
from torrcast.domain.tune import tune
from torrcast.ports.state_store import slot as state_slot
from torrcast.usecases.reinforce.plan_for import plan_for
from torrcast.usecases.select.plan import Plan
from web.request import Request
from web.warm_cache import WarmCache

STATIC = Path(__file__).resolve().parents[2] / "web" / "static"
CARD_JS = (STATIC / "card.js").read_text(encoding="utf-8")
SERIES_JS = (STATIC / "card-series.js").read_text(encoding="utf-8")
GIB = 1024**3
#: Приставка стенда: HEVC она копирует, и сезон вне отбора карточки судится её профилем.
PROFILE: Profile = PROFILES["androidtv"]
CONFIG = tune(Config(receiver_profile="androidtv"), PROFILE)


def _release(name: str, quality: str, codec: str, seeders: int, digit: str, season: int) -> Release:
    return Release(
        raw_name=name,
        title="Show",
        kind="tv",
        seasons=(season,),
        quality=quality,
        codec=codec,
        voices=("rus",),
        size=GIB,
        seeders=seeders,
        episodes=tuple(range(1, 9)),
        magnet="magnet:?xt=urn:btih:" + digit * 40,
    )


FIRST = _release("Show S01 1080p", "1080p", "H.264", 50, "1", 1)
AVC = _release("Show [S02E01-08 of 8] 1080p AVC", "1080p", "H.264", 100, "a", 2)
HEVC = _release("Show [S02E01-08 of 8] 1080p HEVC", "1080p", "HEVC", 300, "b", 2)
PICTURE = Picture(title="Show", year=2020, kind="tv", releases=[FIRST, AVC, HEVC])


@dataclass
class _Voices:
    asked: list[Entry | None] = field(default_factory=list)

    def of(self, _plan: Plan, _query: str, _config: object, live: Entry | None) -> Any:
        self.asked.append(live)
        return None, False

    def profile_of(self, config: Config) -> Profile:
        return PROFILES[config.receiver_profile]


@dataclass
class _Files:
    asked: list[str] = field(default_factory=list)

    def table(self, release: Release, _base_url: str) -> list[list[int]]:
        self.asked.append(info_hash(release) or "")
        return [[2, episode] for episode in range(1, 9)]


class _Facts:
    def start(self) -> None:
        return None

    def ready(self, _title: str, _year: int | None) -> Fact:
        return Fact()

    def answered(self, _title: str, _year: int | None) -> bool:
        return True


class _Related:
    def of(self, _title: str, _series: bool) -> None:
        return None

    def waiting(self, _title: str, _series: bool) -> bool:
        return False


class _Poster:
    def of(self, _picture: Picture) -> tuple[None, bool]:
        return None, False


class _ShowWarm:
    def __init__(self, circle: list[Plan]) -> None:
        self.circle = circle

    def ready(self, _query: str) -> list[Plan]:
        return self.circle


def _card_circle() -> list[Plan]:
    return [plan_for(copy.deepcopy(PICTURE), parse_args(["show"]), CONFIG, PROFILE, 2700.0)]


def _card_body(
    monkeypatch: pytest.MonkeyPatch, entry: Entry | None
) -> tuple[dict[str, Any], _Files]:
    files, circle = _Files(), _card_circle()
    monkeypatch.setattr(card_page, "load_config", lambda: Config(receiver_profile="androidtv"))
    monkeypatch.setattr(card_page, "_voices", _Voices())
    monkeypatch.setattr(card_page, "_episodes", files)
    monkeypatch.setattr(card_page, "_related", _Related())
    monkeypatch.setattr(card_page, "_poster", _Poster())
    monkeypatch.setattr(card_page, "MenuFacts", lambda *_a, **_k: _Facts())
    monkeypatch.setattr(
        card_page,
        "WARM",
        WarmCache(circle=lambda *_a: circle, blurbs=lambda _p: None, spawn=lambda _j: None),
    )
    store = FakeStateStore()
    if entry is not None:
        state = store.load()
        state.entries[PICTURE.key] = entry
        store.save(state)
    state_slot.install(store)
    answer = card_page.card(
        Request("GET", f"/api/card/{PICTURE.key}", {"query": "show", "season": "2"}, {})
    )
    body: dict[str, Any] = json.loads(answer.body)
    return body, files


def _page_sends_the_tab_release() -> bool:
    """Строка серии шлёт ``release`` тела, отрисовавшего вкладку, и для сериала тоже.

    Список не как у раздач (``layout``) раздачи вкладки не шлёт: строку ищут сквозным номером.
    """
    # Обработчик строки назван, потому что гашение по приговору его снимает
    # (:mod:`web.episode_absent`); тело `_play` у него прежнее.
    row = "const play = () => TCCard._play(data, key, query,"
    bound = "if (!grey) row.addEventListener('click', play);" in SERIES_JS
    play = CARD_JS.split("  _play(data, key, query, voices, fromStart, season, episode) {", 1)[1]
    play = play.split("\n  },", 1)[0]
    keys = re.search(r"_keys\(data, key\) \{\s*return \{[^}]*release: data\.release", CARD_JS)
    sends = "release: layout ? undefined : keys.release," in play
    return row in SERIES_JS and bound and sends and keys is not None


def _show_plays(monkeypatch: pytest.MonkeyPatch, release: str) -> tuple[str | None, str]:
    """Раздача, которую показ строки s2e1 спросит первой, и ``--card-release`` его ``argv``."""
    argv = play_argv("show", None, None, 2, 1, False, True, picture=PICTURE.key, release=release)
    args = parse_args(argv)
    monkeypatch.setattr(show_stage, "WARM", _ShowWarm(_card_circle()))
    monkeypatch.setattr(show_stage, "search_circle", lambda *_rest: [])
    circle = show_stage._card_circle(CONFIG, args, FakeProgress(), PROFILE)
    plan = next(plan for plan in circle if plan.picture.key == PICTURE.key)
    first = plan.candidates(args)[0]
    return info_hash(plan.ranked[first - 1]), args.card_release or ""


def test_an_episode_row_plays_the_release_whose_files_listed_its_season(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, files = _card_body(monkeypatch, None)

    assert files.asked == [body["release"]], "список серий построен файлами другой раздачи"
    assert _page_sends_the_tab_release()
    plays, sent = _show_plays(monkeypatch, body["release"])
    assert sent == body["release"]
    assert plays == body["release"]
    natural, _unpinned = _show_plays(monkeypatch, "")
    assert natural == body["release"] == info_hash(HEVC), "вкладка судила не профилем приёмника"


def test_a_bookmark_season_row_plays_the_bookmark_release(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = Entry("Show", AVC.magnet, kind="tv", season=2, episode=1, episodes=[[2, 1, 0, 0]])
    body, files = _card_body(monkeypatch, entry)

    assert body["release"] == info_hash(AVC)
    assert files.asked == [body["release"]]
    plays, sent = _show_plays(monkeypatch, body["release"])
    assert sent == body["release"]
    assert plays == body["release"], "показ сыграл не раздачу закладки, которую назвала вкладка"
    assert _show_plays(monkeypatch, "")[0] != body["release"], "без --card-release звено не мерится"
