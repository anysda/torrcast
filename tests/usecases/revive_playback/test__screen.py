"""Зеркало строк экрана: что показ говорит вслух и что кладёт в состояние."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes import composition
from tests.fakes.clock import FakeClock
from tests.usecases.revive_playback.world import feed_with_segments
from torrcast.domain.entry import Entry
from torrcast.domain.position import Position
from torrcast.usecases.revive_playback._revival import _Revival
from torrcast.usecases.revive_playback._screen import (
    _first_frame,
    _note_transitions,
    _note_watch,
    _report,
)
from torrcast.usecases.revive_playback._screen_state import _Screen
from torrcast.usecases.watch import Watch


def _at(pos: float, state: str) -> Position:
    return Position(pos, 7200.0, state in {"PLAYING", "BUFFERING"}, state)


def test_the_word_playing_alone_is_not_a_picture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Приёмник объявил себя играющим, а указатель стоит - кадра ещё не было."""
    marked: list[Path] = []
    composition.use_playing_mark(monkeypatch, marked.append)
    screen, feed = _Screen(), feed_with_segments(tmp_path)

    _first_frame(screen, feed, _at(120.0, "PLAYING"), "[сеанс]")

    assert (screen.seen, screen.still_at) == (False, 120.0)
    assert marked == [], "флажок картинки ставится по кадру, а не по слову приёмника"


def test_a_moved_pointer_proves_the_picture_and_raises_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Указатель сдвинулся - это и есть кадр: флажок ставится, а не взятый старт называется."""
    marked: list[Path] = []
    composition.use_playing_mark(monkeypatch, marked.append)
    screen, feed = _Screen(raised=False), feed_with_segments(tmp_path)

    _first_frame(screen, feed, _at(120.0, "PLAYING"), "[сеанс]")
    _first_frame(screen, feed, _at(122.0, "PLAYING"), "[сеанс]")

    assert (screen.seen, screen.raised) == (True, True)
    assert marked == [feed.out]
    assert "картинка пошла с 0:02:02" in capsys.readouterr().out


def test_the_rebuffer_is_written_on_entering_it_and_not_every_poll(tmp_path: Path) -> None:
    """Ребуфер - вход в ``BUFFERING``: иначе счётчик считал бы секунды, а не подвисы."""
    screen, feed = _Screen(), feed_with_segments(tmp_path)

    _note_transitions(screen, feed, _at(10.0, "BUFFERING"))

    assert screen.buffering is True

    _note_transitions(screen, feed, _at(10.0, "BUFFERING"))
    _note_transitions(screen, feed, _at(12.0, "PLAYING"))

    assert screen.buffering is False


def test_the_offline_mark_follows_the_packing(tmp_path: Path) -> None:
    """Обрыв замечает упаковка, а признак «уже сказано» ходит за ней по переходам."""
    screen, feed = _Screen(), feed_with_segments(tmp_path)
    feed.offline = "сети нет"

    _note_transitions(screen, feed, _at(10.0, "PLAYING"))

    assert screen.was_offline is True

    feed.offline = ""
    _note_transitions(screen, feed, _at(12.0, "PLAYING"))

    assert screen.was_offline is False


def test_the_darkness_is_reported_by_its_own_line_and_not_by_a_position(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """В темноте не отчитываются позицией: кадра на экране нет, а числа были бы те же."""
    revival = _Revival(clock=FakeClock(now=1100.0), since=1000.0, why="сети нет")

    _report("[сеанс]", revival, _at(72.0, "IDLE"), feed_with_segments(tmp_path), None)
    printed = capsys.readouterr().out

    assert "темнота 0:01:40 (сети нет) - картинки нет" in printed
    assert "источник не вернулся - приёмник не трогаю" in printed
    assert "экран:" not in printed


def test_a_live_screen_is_reported_by_what_the_receiver_sees(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Показ идёт - строка называет позицию и длительность, снятые у приёмника."""
    revival = _Revival(clock=FakeClock(now=1000.0))

    _report("[сеанс]", revival, _at(72.0, "PLAYING"), feed_with_segments(tmp_path), None)

    assert "[сеанс] экран: 0:01:12 из 2:00:00 · PLAYING" in capsys.readouterr().out


def test_the_bookmark_and_the_darkness_reach_the_state() -> None:
    """Наружу уходят показанный кадр и правда о чёрном экране - и не по тику, а на переходе."""
    watch = Watch(key="кино", entry=Entry(title="Кино", magnet="magnet:?xt=1"))
    revival = _Revival(clock=FakeClock(now=1000.0), began=17.0, why="сети нет")

    _note_watch(watch, None, 120.0, revival)

    assert (watch.entry.dark, watch.entry.dark_why) == (17.0, "сети нет")
