"""Зеркало отказа до юнита: кадр, который приёмник не берёт, не поднимает ни ffmpeg, ни раздачу."""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from tests.fakes import composition
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.profile import BROWSER, CAUTIOUS
from torrcast.usecases.playback._refuse_hopeless import _refuse_hopeless


def test_a_frame_the_receiver_never_takes_is_refused_before_the_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4К без перекода приёмник не берёт вовсе - отказ печатается до всякого ffmpeg."""
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))
    config = Config(recode=False)
    entry = Entry(title="Кино", magnet="magnet:?xt=1", frame=2160, quality="2160p")

    want = phrase("playback.frame_too_big", quality="2160p", limit=CAUTIOUS.recode_frame)
    with pytest.raises(NotFoundError, match=re.escape(want)):
        _refuse_hopeless(config, entry)


def test_the_same_record_plays_when_the_whole_recode_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ужать кадр умеет сплошной перекод - значит отказывать тут нечему."""
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))

    _refuse_hopeless(Config(recode=True), Entry(title="Кино", magnet="magnet:?xt=1", frame=2160))


def test_a_record_of_an_older_version_plays_as_it_did(monkeypatch: pytest.MonkeyPatch) -> None:
    """Кадр ноль - запись прежней версии: молчим там, где не знаем."""
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))

    _refuse_hopeless(Config(recode=False), Entry(title="Кино", magnet="magnet:?xt=1"))


@pytest.mark.parametrize(("tab", "refused"), [("chromium-linux", True), ("", False)])
def test_the_frame_limit_is_the_one_of_the_profile_the_tab_plays(
    monkeypatch: pytest.MonkeyPatch, tab: str, refused: bool
) -> None:
    """Предел кадра - у профиля показа: замеренная вкладка сыграет :data:`BROWSER`, и
    отказ судит им, а не тем, что детектор выбрал бы без её ключа."""
    wide = replace(CAUTIOUS, recode_frame=2160)
    composition.use_profile(monkeypatch, lambda config: Choice(wide, "паспорта нет"))
    config = Config(receiver="browser", recode=False)
    entry = Entry(title="Кино", magnet="magnet:?xt=1", frame=2160, quality="2160p")

    if refused:
        with pytest.raises(NotFoundError, match=str(BROWSER.recode_frame)):
            _refuse_hopeless(config, entry, tab)
    else:
        _refuse_hopeless(config, entry, tab)
