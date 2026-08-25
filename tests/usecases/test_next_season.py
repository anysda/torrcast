"""Зеркало :mod:`torrcast.usecases.next_season`: конец сезона - поиск следующего, а не стена.

Единица отвечает на один вопрос - продолжается ли сериал за границей раздачи сезона, -
и каждый её ответ обязан быть слышен: на стыке сезонов консоли нет, и молчание там -
это погасший экран без единого слова (TC-805).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes.state_store import FakeStateStore
from tests.fakes.torrent_engine import FakeTorrentEngine
from torrcast.domain._series import _Series
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.episode import Episode
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.state_store.slot import install, store
from torrcast.usecases.next_season import _next_season
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select.plan import Plan

KEY = "tv:сериал:2020"


@pytest.fixture(autouse=True)
def _state() -> None:
    """Состояние держит порт, а не файл: вопрос про следующий сезон диска не трогает."""
    install(FakeStateStore())


def _put(**fields: Any) -> Entry:
    """Кладёт в состояние досмотренную запись сезона под ключом показа."""
    base: dict[str, Any] = {
        "title": "Сериал",
        "magnet": "magnet:?xt=сезон-4",
        "kind": "tv",
        "season": 4,
        "episode": 10,
        "done": True,
        "episodes": [[4, 9, 0, 10**9], [4, 10, 1, 10**9]],
        "query": "сериал",
    }
    base.update(fields)
    entry = Entry(**base)
    keeper = store()
    state = keeper.load()
    state.put(KEY, entry)
    keeper.save(state)
    return entry


def _plan() -> Plan:
    """План той же картины с паком пятого сезона: цель - s5e1."""
    pack = Release(
        raw_name="Сериал / Serial (Сезон 5) WEB-DL 1080p",
        title="Сериал",
        year=2020,
        quality="1080p",
        codec="H.264",
        voices=("MVO",),
        size=16 * 1024**3,
        seeders=50,
        magnet="magnet:?xt=сезон-5",
    )
    return Plan(
        picture=Picture(title="Сериал", year=2020, kind="tv", releases=[pack]),
        ranked=[pack],
        runtime=1400.0,
        warn_mbit=16.0,
        series=_Series(want=Episode(5, 1)),
    )


def _prep(plan: Plan) -> _Prep:
    """Готовый к показу пак пятого сезона: файл и дорожки уже прочитаны."""
    files = [
        TorrFile(index=0, name="сериал/s05e01.mkv", size=8 * 1024**3),
        TorrFile(index=1, name="сериал/s05e02.mkv", size=8 * 1024**3),
    ]
    prep = _Prep(number=1, release=plan.ranked[0])
    prep.video, prep.files = files[0], files
    prep.media = Media(
        duration=1400.0,
        tracks=(AudioTrack(index=0, language="rus", title="MVO"),),
        video="h264",
        height=1080,
        video_bps=8.0 * 1e6,
    )
    return prep


class _Bench:
    """Стенд отбора под наблюдением зеркала: отвечает готовым релизом или отказом."""

    def __init__(self, prep: _Prep | None = None, refusal: Exception | None = None) -> None:
        self.prep, self.refusal = prep, refusal
        self.dropped = 0
        self.kept: _Prep | None = None

    def resolve(self, *_args: object, **_rest: object) -> _Prep:
        if self.refusal is not None:
            raise self.refusal
        assert self.prep is not None
        return self.prep

    def drop_all(self) -> None:
        self.dropped += 1

    def keep_only(self, chosen: _Prep) -> None:
        self.kept = chosen


def test_a_finished_season_searches_and_records_the_next_one() -> None:
    """Досмотрели s4e10 - в состоянии ложится s5e1 новой раздачи, и цикл её играет."""
    _put()
    plan = _plan()
    prep = _prep(plan)
    asked: list[Args] = []

    def circle(_config: object, args: Args, *_rest: object, **_kw: object) -> list[Plan]:
        asked.append(args)
        return [plan]

    found = _next_season(
        Config(),
        KEY,
        FakeTorrentEngine(),
        CAUTIOUS,
        circle=circle,
        stand=lambda *_a, **_k: _Bench(prep),  # type: ignore[arg-type]
    )

    assert found is True
    assert str(asked[0].episode) == "s5e1", "ищется первая серия следующего сезона"
    entry = store().load().get(KEY)
    assert entry is not None
    assert (entry.season, entry.episode, entry.done) == (5, 1, False)
    assert entry.magnet == "magnet:?xt=сезон-5", "играть цикл будет новую раздачу"
    assert entry.label == "s5e1"


def test_a_missing_next_season_says_the_season_was_the_last(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Следующего сезона в природе нет - честная строка, а не молчаливый выход."""
    _put()

    def circle(*_args: object, **_kw: object) -> list[Plan]:
        raise NotFoundError("«Сериал»: раздач с сезоном 5 нет")

    found = _next_season(Config(), KEY, FakeTorrentEngine(), CAUTIOUS, circle=circle)

    assert found is False
    assert "«Сериал» - сезон 4 последний" in capsys.readouterr().out
    entry = store().load().get(KEY)
    assert entry is not None and entry.done, "запись досмотренного сезона не тронута"


def test_a_picture_absent_from_the_answer_is_the_same_last_season(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Выдача ответила, но картины в ней нет - раздач следующего сезона не нашлось."""
    _put()

    found = _next_season(Config(), KEY, FakeTorrentEngine(), CAUTIOUS, circle=lambda *_a, **_k: [])

    assert found is False
    assert "сезон 4 последний" in capsys.readouterr().out


def test_a_season_that_cannot_be_played_names_the_refusal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Сезон нашёлся, но играть его нечем - строка называет причину отбора."""
    _put()
    bench = _Bench(refusal=NotFoundError("рой мёртв"))

    found = _next_season(
        Config(),
        KEY,
        FakeTorrentEngine(),
        CAUTIOUS,
        circle=lambda *_a, **_k: [_plan()],
        stand=lambda *_a, **_k: bench,  # type: ignore[arg-type]
    )

    assert found is False
    assert "сезон 5 не поднялся: рой мёртв" in capsys.readouterr().out
    assert bench.dropped == 1, "прогретое без показа убрано"


@pytest.mark.parametrize(
    "fields",
    [
        {"done": False},  # запись живая: это стык серий, а не конец сезона
        {"kind": "movie", "season": None, "episode": None, "episodes": []},  # фильм
    ],
)
def test_anything_but_a_finished_season_is_not_looked_beyond(fields: dict[str, Any]) -> None:
    """Поиск следующего сезона не зовётся там, где сезон не кончился."""
    _put(**fields)

    def circle(*_args: object, **_kw: object) -> list[Plan]:
        raise AssertionError("поиску тут делать нечего")

    assert _next_season(Config(), KEY, None, CAUTIOUS, circle=circle) is False  # type: ignore[arg-type]


def test_an_unknown_key_is_a_quiet_no() -> None:
    """Запись могли снести между сторожем и циклом - это не авария и не поиск."""
    assert _next_season(Config(), "tv:такого-нет:1900", FakeTorrentEngine(), CAUTIOUS) is False
