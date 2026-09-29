"""Показ с карточки ищет картину тем же правилом, каким её нашла карточка."""

from __future__ import annotations

from typing import Any

import pytest

import web.show_stage as show_stage
from tests.usecases.cast_command.world import plans
from torrcast.domain.args import Args
from torrcast.domain.not_found_error import NotFoundError


class _Circles:
    """Круг по строке: у строки плитки картины нет, у имени из ключа она есть."""

    def __init__(self, circles: dict[str, Any], alike: dict[str, Any] | None = None) -> None:
        self.circles, self.asked = circles, []  # type: dict[str, Any], list[str]
        self.alike = alike or {}

    def live(self, query: str, alike: bool = False) -> Any:
        return self.alike.get(query) if alike else None

    def ready(self, query: str) -> None:
        return None  # круг ещё идёт: показ не знает его итога

    def take(self, query: str, retry: bool = False) -> Any:
        self.asked.append(query)
        found = self.circles[query]
        if isinstance(found, Exception):
            raise found
        return found


def test_a_play_pressed_before_the_card_answered_finds_the_picture_by_its_key_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Оно» 2017: по «Оно» фильма нет, по «оно» из ключа есть - играет он, а не отказ."""
    tile, own = plans(2), plans(3)
    key = own[2].picture.key
    monkeypatch.setattr(show_stage, "WARM", _Circles({"Оно": tile, own_name(key): own}))

    got = show_stage._card_circle(Any, Args(query=["Оно"], picture=key), Any, Any)  # type: ignore[arg-type]

    assert [p.picture.key for p in got] == [p.picture.key for p in own]
    assert show_stage._card_picture(got, key) == 3


def test_a_refused_tile_line_still_leaves_the_key_name(monkeypatch: pytest.MonkeyPatch) -> None:
    own = plans(1)
    key = own[0].picture.key
    circles = _Circles({"Оно": NotFoundError("Оно"), own_name(key): own})
    monkeypatch.setattr(show_stage, "WARM", circles)

    got = show_stage._card_circle(Any, Args(query=["Оно"], picture=key), Any, Any)  # type: ignore[arg-type]

    assert [p.picture.key for p in got] == [key]


def test_a_picture_gone_from_every_line_keeps_the_tile_circle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Нет картины нигде - круг плитки, и показ честно говорит «картины больше нет»."""
    tile = plans(2)
    circles = _Circles({"Оно": tile, "никто": plans(1)})
    monkeypatch.setattr(show_stage, "WARM", circles)

    got = show_stage._card_circle(Any, Args(query=["Оно"], picture="movie:никто:1900"), Any, Any)  # type: ignore[arg-type]

    assert [p.picture.key for p in got] == [p.picture.key for p in tile]
    assert show_stage._card_picture(got, "movie:никто:1900") == 0


def test_a_history_tile_line_plays_the_warm_circle_of_the_same_spelling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Рататуй»: «Играть» с плитки истории несёт «рататуй» - сети нет, круг согретый."""
    own = plans(2)
    key = own[1].picture.key
    circles = _Circles({}, alike={own_name(key): own})
    monkeypatch.setattr(show_stage, "WARM", circles)

    got = show_stage._card_circle(Any, Args(query=[own_name(key)], picture=key), Any, Any)  # type: ignore[arg-type]

    assert [p.picture.key for p in got] == [p.picture.key for p in own]
    assert circles.asked == []


def own_name(key: str) -> str:
    return key.split(":")[1].replace("-", " ")
