"""``argv`` показа: старый вызов не меняется, новые доводы добавляют свои токены."""

from __future__ import annotations

from hass.play_argv import play_argv
from torrcast.cli.parse_args import parse_args


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
        "s1e4",
        "--pick",
        "2",
        "--voice",
        "LostFilm",
        "--new",
    ]


def test_the_argv_of_every_combination_is_one_the_cli_actually_reads() -> None:
    """🔴 Форму ``argv`` судит САМ разбор CLI, а не соседний список в зеркале.

    Список ожидаемых слов проверяет мою же догадку о порядке, и она была неверной: серия
    после ``--pick`` уезжала в позиционные доводы за флагом, а их argparse объявляет
    лишними (``unrecognized arguments: s1e2``) и уходит из процесса через ``SystemExit``.
    Единственный честный судья порядка - тот, кому этот ``argv`` и адресован.
    """
    for pick in (None, 2):
        for voice in (None, "LostFilm"):
            for season, episode in ((None, None), (1, 4)):
                for from_start in (False, True):
                    argv = play_argv("шоу", pick, voice, season, episode, from_start)
                    read = parse_args(argv)
                    assert read.query[0] == "шоу", argv
                    assert read.pick == pick, argv
