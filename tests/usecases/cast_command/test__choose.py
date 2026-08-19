"""Зеркало пути до релиза: закладка выбранной картины отвечает показом прямо отсюда."""

from __future__ import annotations

from typing import Any, cast

import pytest

from tests.fakes import composition
from tests.usecases.cast_command.world import entry, plan
from torrcast.domain.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._choose import _choose
from torrcast.usecases.choice._passport import _Passport
from torrcast.usecases.select_bench import Bench
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


@pytest.fixture(autouse=True)
def _outside(monkeypatch: pytest.MonkeyPatch) -> None:
    """Справка и служба раздач - от корня подделкой; сеть и рой за ними не стоят."""
    composition.use_facts(monkeypatch, _Facts)
    composition.use_engines(monkeypatch, lambda url, timeout=30.0: object())


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


def test_a_saved_place_of_the_chosen_picture_answers_with_a_code() -> None:
    """Закладка выбранной картины отвечает показом сама - и код уезжает наружу целым."""
    state = WatchState()
    state.put(plan().picture.key, entry())

    picked = _choose(
        Config(),
        cast(Any, Args(query=["кино"])),
        Choice(profile=CAUTIOUS, how="стенд"),
        state,
        None,
        _Clock(),
        circle=lambda *args, **rest: [plan()],
        stand=lambda *args, **rest: cast(Bench, _NoBench()),
        passport_of=lambda plans: cast(_Passport, _NoPassport()),
        pick=lambda *args, **rest: plan(),
        bookmark=lambda *args, **rest: EXIT_OK,
    )

    assert picked == EXIT_OK
