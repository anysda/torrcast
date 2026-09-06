"""``argv`` показа: старый вызов не меняется, новые доводы добавляют свои токены."""

from __future__ import annotations

from hass.play_argv import play_argv


def test_the_bare_old_call_stays_a_single_word() -> None:
    assert play_argv("матрица", None, None, None, None, False) == ["матрица"]


def test_a_pick_adds_its_own_flag() -> None:
    assert play_argv("матрица", 2, None, None, None, False) == ["матрица", "--pick", "2"]


def test_a_season_and_episode_add_the_token_the_cli_already_parses() -> None:
    assert play_argv("шоу", None, None, 1, 4, False) == ["шоу", "s1e4"]


def test_a_lone_season_or_episode_adds_nothing() -> None:
    assert play_argv("шоу", None, None, 1, None, False) == ["шоу"]
    assert play_argv("шоу", None, None, None, 4, False) == ["шоу"]


def test_a_voice_adds_the_flag_the_cli_understands() -> None:
    assert play_argv("матрица", None, "LostFilm", None, None, False) == [
        "матрица",
        "--voice",
        "LostFilm",
    ]


def test_from_start_adds_the_flag_the_cli_already_reads() -> None:
    assert play_argv("матрица", None, None, None, None, True) == ["матрица", "--new"]


def test_every_extra_combines_in_the_order_the_cli_expects() -> None:
    assert play_argv("шоу", 2, "LostFilm", 1, 4, True) == [
        "шоу",
        "--pick",
        "2",
        "s1e4",
        "--voice",
        "LostFilm",
        "--new",
    ]
