"""Зеркало починки автозамены дефиса флага на тире клиента Telegram."""

from __future__ import annotations

from tgbot.restore_flag_dashes import restore_flag_dashes
from torrcast.cli.parse_args import parse_args


def test_em_dash_at_word_start_becomes_a_double_hyphen() -> None:
    assert restore_flag_dashes("мумия —menu") == "мумия --menu"


def test_en_dash_at_word_start_becomes_a_double_hyphen_too() -> None:
    """Среднее тире рождается из пары дефисов, а не из одного."""
    assert restore_flag_dashes("мумия –menu") == "мумия --menu"


def test_horizontal_bar_at_word_start_becomes_a_double_hyphen() -> None:
    assert restore_flag_dashes("мумия ―menu") == "мумия --menu"


def test_a_flag_with_a_value_survives_the_en_dash_and_is_read_by_the_parser() -> None:
    """🔴 Одиночная трактовка давала `-pick`, которого argparse не знает вовсе."""
    restored = restore_flag_dashes("мумия –pick 2")

    assert restored == "мумия --pick 2"
    assert parse_args(restored.split()).pick == 2


def test_dash_surrounded_by_spaces_inside_a_title_is_left_alone() -> None:
    """Типографское тире в названии картины окружено пробелами с обеих сторон."""
    assert restore_flag_dashes("человек — паук") == "человек — паук"


def test_leading_dash_is_normalised_too() -> None:
    assert restore_flag_dashes("—menu мумия") == "--menu мумия"
