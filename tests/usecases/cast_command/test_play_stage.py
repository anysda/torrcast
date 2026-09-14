"""Круг показа и картина по ключу: без моста страницы - консольные."""

from __future__ import annotations

from tests.usecases.cast_command.world import plans
from torrcast.usecases.cast_command.play_stage import (
    PlayStage,
    _configure_play_stage,
    _exact_picture,
    _play_stage,
)
from torrcast.usecases.discover.search_circle import search_circle


def test_without_the_page_the_show_searches_itself_and_matches_keys_exactly() -> None:
    menu = plans(3)

    assert _play_stage().circle is search_circle
    assert _exact_picture(menu, menu[1].picture.key) == 2
    assert _exact_picture(menu, "movie:никто:1900") == 0


def test_the_page_puts_its_own_circle_and_rule_in_place() -> None:
    before = _play_stage()
    page = PlayStage(circle=lambda *_rest: [], picture=lambda plans, key: 1)
    try:
        _configure_play_stage(page)
        assert _play_stage() is page
    finally:
        _configure_play_stage(before)
