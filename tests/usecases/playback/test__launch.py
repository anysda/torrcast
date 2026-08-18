"""Зеркало запуска показа: отказ безнадёжному, юнит и ожидание КАРТИНКИ, а не упаковки."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

import torrcast.usecases.playback._show_state as _state
from tests.fakes.clock import FakeClock
from tests.usecases.playback.world import FakeProgress, FakeShow, touch_segment
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.profile import CAUTIOUS
from torrcast.ports.show_unit import ShowUnit
from torrcast.usecases.playback._launch import _await_playing, _refuse_hopeless


def test_a_frame_the_receiver_never_takes_is_refused_before_the_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4К без перекода приёмник не берёт вовсе - отказ печатается до всякого ffmpeg."""
    monkeypatch.setattr(_state, "detect_profile", lambda config: Choice(CAUTIOUS, "стенд"))
    config = Config(recode=False)
    entry = Entry(title="Кино", magnet="magnet:?xt=1", frame=2160, quality="2160p")

    with pytest.raises(NotFoundError, match="такой кадр приёмник берёт только ужатым"):
        _refuse_hopeless(config, entry)


def test_the_same_record_plays_when_the_whole_recode_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ужать кадр умеет сплошной перекод - значит отказывать тут нечему."""
    monkeypatch.setattr(_state, "detect_profile", lambda config: Choice(CAUTIOUS, "стенд"))

    _refuse_hopeless(Config(recode=True), Entry(title="Кино", magnet="magnet:?xt=1", frame=2160))


def test_a_record_of_an_older_version_plays_as_it_did(monkeypatch: pytest.MonkeyPatch) -> None:
    """Кадр ноль - запись прежней версии: молчим там, где не знаем."""
    monkeypatch.setattr(_state, "detect_profile", lambda config: Choice(CAUTIOUS, "стенд"))

    _refuse_hopeless(Config(recode=False), Entry(title="Кино", magnet="magnet:?xt=1"))


def test_the_flag_of_the_picture_ends_the_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ждут КАРТИНКУ: флажок кладёт юнит, и ровно по нему ожидание кончается."""
    out = tmp_path / "hls"
    out.mkdir()
    (out / "playing").write_text("")
    monkeypatch.setattr(_state, "playing_flag", lambda where: Path(where) / "playing")
    progress = FakeProgress()

    _await_playing(
        Config(hls_dir=str(out)),
        progress,
        5.0,
        clock=FakeClock(now=100.0),
        unit=cast(ShowUnit, FakeShow()),
    )

    assert progress.phases[-1] == ""


def test_a_dead_unit_ends_the_waiting_with_its_own_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Юнит выпал - ждать нечего, и причина берётся у него же, а не выдумывается."""
    out = tmp_path / "hls"
    touch_segment(out)
    monkeypatch.setattr(_state, "playing_flag", lambda where: Path(where) / "playing")

    with pytest.raises(InfraError, match="показ не запустился: юнит выпал"):
        _await_playing(
            Config(hls_dir=str(out)),
            FakeProgress(),
            5.0,
            clock=FakeClock(now=100.0),
            unit=cast(ShowUnit, FakeShow(alive=False, reason="юнит выпал")),
        )


def test_the_budget_of_the_start_is_not_endless(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Бюджет старта вышел - юнит гасится, а человеку называется срок, а не молчание."""
    out = tmp_path / "hls"
    out.mkdir()
    monkeypatch.setattr(_state, "playing_flag", lambda where: Path(where) / "playing")
    unit = FakeShow()

    with pytest.raises(InfraError, match="показ не начался за 3 с"):
        _await_playing(
            Config(hls_dir=str(out)),
            FakeProgress(),
            3.0,
            clock=FakeClock(now=100.0),
            unit=cast(ShowUnit, unit),
        )

    assert unit.stopped == 1, "юнит, не давший картинки, обязан быть погашен"
