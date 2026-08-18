"""Зеркало счастливого пути: ранние выходы отвечают показом, а не проваливаются в поиск."""

from __future__ import annotations

import importlib
from typing import Any

import pytest

import torrcast.usecases.cast_command._play_state as _state
from tests.usecases.cast_command.world import entry
from torrcast.domain.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store import store as watch_store
from torrcast.usecases.cast_command._cmd_play import _cmd_play

#: Модуль команды: имя ``_cmd_play`` на пакете занято самой функцией.
_module = importlib.import_module("torrcast.usecases.cast_command._cmd_play")


@pytest.fixture(autouse=True)
def _outside(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(_state, "_play_settings", Config)
    monkeypatch.setattr(_state, "_play_detect", lambda config: Choice(CAUTIOUS, "стенд"))
    monkeypatch.setattr(_module, "_release_orphans", lambda config: None)
    monkeypatch.setattr(_module, "_say_showing", lambda live: None)


def _remember(saved: object) -> None:
    state = WatchState()
    state.put("кино", saved)  # type: ignore[arg-type]
    watch_store().save(state)


def test_a_saved_movie_is_continued_without_a_single_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Начатый фильм продолжается молча: до поиска этот путь не доходит вовсе."""
    monkeypatch.setattr(_module, "_continue", lambda *args, **rest: EXIT_OK)
    monkeypatch.setattr(
        _module, "_choose", lambda *args, **rest: pytest.fail("до поиска доходить нечему")
    )
    _remember(entry(query="кино"))

    assert _cmd_play(Args(query=["кино"])) == EXIT_OK


def test_a_watched_movie_is_started_over_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Досмотренный фильм играется с начала - и это тоже ранний выход, а не поиск."""
    monkeypatch.setattr(_module, "_from_start", lambda *args, **rest: EXIT_OK)
    monkeypatch.setattr(
        _module, "_choose", lambda *args, **rest: pytest.fail("до поиска доходить нечему")
    )
    _remember(entry(query="кино", pos=7100.0))

    assert _cmd_play(Args(query=["кино"])) == EXIT_OK


def test_the_code_of_the_bookmark_of_the_chosen_picture_reaches_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Закладка выбранной картины отвечает показом - и её код уезжает наружу целым."""
    monkeypatch.setattr(_module, "_choose", lambda *args, **rest: EXIT_OK)

    assert _cmd_play(Args(query=["кино"])) == EXIT_OK
