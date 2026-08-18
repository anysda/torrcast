"""Зеркало пути до релиза: закладка выбранной картины отвечает показом прямо отсюда."""

from __future__ import annotations

import importlib
from typing import Any, cast

import pytest

import torrcast.usecases.cast_command._play_state as _state
from tests.usecases.cast_command.world import entry, plan
from torrcast.cli.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._choose import _choose
from torrcast.usecases.start_clock import _Clock


class _Facts:
    """Справка, которой нечего сказать: путь до релиза считает по своим числам."""

    def __init__(self, wanted: object) -> None:
        self.wanted = wanted

    def start(self) -> None:
        return None

    def finish(self) -> None:
        return None

    def get(self, *_rest: object) -> Any:
        from torrcast.domain.facts.fact import Fact

        return Fact()


#: Модуль пути до релиза: имя ``_choose`` на пакете занято самой функцией, поэтому
#: зеркало спрашивает модуль по полному имени, а не через атрибут пакета.
_choose_module = importlib.import_module("torrcast.usecases.cast_command._choose")


@pytest.fixture(autouse=True)
def _outside(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_state, "_play_facts", _Facts)
    monkeypatch.setattr(_state, "_play_engines", lambda url: object())
    monkeypatch.setattr(_choose_module, "_search", lambda *args, **rest: [plan()])
    monkeypatch.setattr(_choose_module, "_Bench", lambda *args, **rest: _NoBench())
    monkeypatch.setattr(_choose_module, "_passport", lambda plans: _NoPassport())


class _NoBench:
    """Стенд отбора, который ничего не греет: зеркало меряет решение, а не рой."""

    def start(self, plan: object, number: int) -> None:
        return None

    def spare(self, plan: object, args: object) -> None:
        return None

    def drop_all(self) -> None:
        return None


class _NoPassport:
    def get(self) -> Any:
        from torrcast.domain.facts.origin import Origin

        return Origin()


def test_a_saved_place_of_the_chosen_picture_answers_with_a_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Закладка выбранной картины отвечает показом сама - и код уезжает наружу целым."""
    monkeypatch.setattr(_choose_module, "_pick_plan", lambda *args, **rest: plan())
    monkeypatch.setattr(_choose_module, "_continue_picked", lambda *args, **rest: EXIT_OK)
    state = WatchState()
    state.put(plan().picture.key, entry())

    picked = _choose(
        Config(),
        cast(Any, Args(query=["кино"])),
        Choice(profile=CAUTIOUS, how="стенд"),
        state,
        None,
        _Clock(),
    )

    assert picked == EXIT_OK
