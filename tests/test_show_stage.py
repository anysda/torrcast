"""Показ с карточки берёт круг карточки, а не заводит второй рядом."""

from __future__ import annotations

import threading
from typing import Any

import pytest

import web.show_stage as show_stage
from tests.usecases.cast_command.world import plans
from torrcast.domain.args import Args


class _Warm:
    def __init__(self, circle: list[Any]) -> None:
        self.circle, self.asked = circle, []  # type: list[Any], list[str]

    def take(self, query: str) -> list[Any]:
        self.asked.append(query)
        return self.circle


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
    """Консоль и Home Assistant карточки не называют; и серия меняет сам круг."""
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
