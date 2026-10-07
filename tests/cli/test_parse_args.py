"""Контракт ``cast``: имена флагов, их умолчания и прежнее имя ``--audio``."""

from __future__ import annotations

import pytest

from torrcast.cli.parse_args import TV_MENU, parse_args
from torrcast.domain.rank_settings import VOICE_MENU


def test_a_bare_query_is_all_that_is_needed() -> None:
    args = parse_args(["моана", "2"])

    assert args.query == ["моана", "2"]
    assert (args.tv, args.release, args.file, args.voice) == (None, None, None, None)
    assert not args.from_start and not args.dry


def test_no_query_names_the_show_command_and_status_stays_explicit() -> None:
    """Голый ``cast`` показывает картину; сводку просит только ``cast status``."""
    assert parse_args([]).command == "play"
    assert parse_args(["status"]).command == "status"


def test_from_start_without_a_query_is_the_default_show_from_its_start() -> None:
    args = parse_args(["--new"])

    assert args.command == "play" and args.from_start


def test_tv_without_an_address_asks_for_the_menu() -> None:
    """``--tv`` без адреса - это меню: значение-заглушка адресом не бывает никогда."""
    assert parse_args(["--tv"]).tv == TV_MENU
    assert parse_args(["--tv", "10.0.0.50"]).tv == "10.0.0.50"


def test_telegram_flag_opens_setup_menu() -> None:
    args = parse_args(["-tg"])
    assert args.telegram
    assert args.command == "telegram"


def test_the_language_flags_name_a_language_and_their_absence_names_none() -> None:
    """``None`` без флага - не мелочь: «не назван» и «назван английский» решаются разно."""
    assert parse_args(["--ru"]).language == "ru"
    assert parse_args(["--en"]).language == "en"
    assert parse_args(["--ru", "мумия"]).language == "ru"
    assert parse_args(["мумия"]).language is None


def test_a_bare_language_flag_is_the_whole_command_and_a_query_next_to_it_is_not() -> None:
    """Голый ``cast --ru`` не сводится ни к пустому поиску, ни к сводке показа."""
    assert parse_args(["--ru"]).command == "language"
    assert parse_args(["--ru", "мумия"]).command == "play"


def test_two_languages_at_once_are_refused_by_the_parser() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--ru", "--en"])


def test_voice_without_a_number_asks_for_the_menu() -> None:
    assert parse_args(["кино", "--voice"]).voice == VOICE_MENU
    assert parse_args(["кино", "--voice", "3"]).voice == 3


def test_a_voice_can_be_named_as_a_studio() -> None:
    assert parse_args(["кино", "--voice", "New Station"]).voice == "New Station"


def test_the_old_audio_flag_still_means_voice() -> None:
    """Прежнее имя флага: ломать чужие пальцы и историю оболочки незачем."""
    assert parse_args(["кино", "--audio", "2"]).voice == 2
    assert parse_args(["кино", "--audio"]).voice == VOICE_MENU


def test_debug_handles_and_the_show_flags_are_read_as_named() -> None:
    args = parse_args(["кино", "--release", "2", "--file", "1", "--pick", "3", "--new", "--dry"])

    assert (args.release, args.file, args.pick) == (2, 1, 3)
    assert args.from_start and args.dry


def test_the_menu_is_asked_by_a_flag_of_its_own() -> None:
    """``--menu`` - просьба выбрать картину: номера у неё нет, и по умолчанию её нет."""
    assert parse_args(["кино", "--menu"]).menu
    assert not parse_args(["кино"]).menu


def test_the_log_border_and_the_unit_key_are_read_as_named() -> None:
    assert parse_args(["log", "--since", "2d"]).since == "2d"
    assert parse_args(["--play-key", "movie:кино:1999"]).play_key == "movie:кино:1999"


def test_flags_are_never_abbreviated() -> None:
    """``--rel 2`` - это не ``--release 2``: сокращения молча меняли бы смысл строки."""
    with pytest.raises(SystemExit):
        parse_args(["кино", "--rel", "2"])


def test_the_version_is_printed_and_the_run_ends(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_code:
        parse_args(["--version"])

    assert exit_code.value.code == 0
    assert capsys.readouterr().out.startswith("torrcast ")
