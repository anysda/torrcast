"""Разбор ``argv`` по контракту ``cast``: единственное место, где живёт argparse.
Зовёт его :func:`torrcast.cli.main.main`, результат читают команды пакета
:mod:`torrcast.cli`.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from torrcast.domain.args import Args
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.tongue import EN, RU
from torrcast.domain.rank_settings import VOICE_MENU
from torrcast.domain.version import __version__

#: Имя флага восстановления - часть контракта командной строки, а не надпись человеку;
#: сам текст справки живёт в каталоге (:mod:`torrcast.domain.catalogs.cli`) и берётся
#: словом :func:`phrase`, чтобы `--help` говорил на языке настройки, а не всегда по-русски.
FROM_START_FLAG = "--new"
#: ``--tv`` без адреса: найти приёмники в сети и показать список. Адресом такое значение
#: не бывает никогда, поэтому путь «адрес назвали руками» остаётся ровно прежним.
TV_MENU = "?"


def _voice(value: str) -> int | str:
    """Номер остаётся номером, всякое другое значение остаётся именем студии."""
    try:
        return int(value)
    except ValueError:
        return value


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """Разобрать argv по контракту CLI.

    Композиционный корень (:func:`torrcast.runtime.wire.wire`) успевает выставить язык
    ДО этого вызова, поэтому :func:`phrase` тут уже отвечает на языке настройки -
    ``cast --help`` говорит по-русски у русской установки и по-английски у английской,
    а не одним и тем же текстом всегда (TC-947).
    """
    parser = argparse.ArgumentParser(
        prog="cast", description=phrase("cli.about"), allow_abbrev=False
    )
    parser.add_argument("query", nargs="*", help=phrase("cli.help_query"))
    parser.add_argument(
        "--tv",
        nargs="?",
        const=TV_MENU,
        metavar="IP",
        help=phrase("cli.help_tv"),
    )
    parser.add_argument(
        "-tg",
        dest="telegram",
        action="store_true",
        help=phrase("cli.help_telegram"),
    )
    # Язык - настройка, а не режим запуска: флаг ЗАПОМИНАЕТСЯ, и следующий `cast` уже
    # говорит на нём же. Умолчание тут `None`, а не "en": «язык не назван» и «назван
    # английский» - разные ответы, и первый обязан взять язык из настройки.
    tongue = parser.add_mutually_exclusive_group()
    tongue.add_argument(
        "--ru",
        dest="language",
        action="store_const",
        const=RU,
        help=phrase("cli.help_ru"),
    )
    tongue.add_argument(
        "--en",
        dest="language",
        action="store_const",
        const=EN,
        help=phrase("cli.help_en"),
    )
    # Номер релиза имеет смысл только вместе с запросом и выбранной картиной: другой
    # запрос - другой список, а у каждой картины в нём - свои номера (TC-446).
    parser.add_argument(
        "--release",
        type=int,
        metavar="N",
        help=phrase("cli.help_release"),
    )
    parser.add_argument("--pick", type=int, metavar="N", help=phrase("cli.help_pick"))
    # Закладка отвечает на «где я остановился», а меню - на «что играть»: этой ручкой
    # спрашивают второе, и сохранённое место у неё дороги не занимает.
    parser.add_argument(
        "--menu",
        action="store_true",
        help=phrase("cli.help_menu"),
    )
    parser.add_argument("--file", type=int, metavar="N", help=phrase("cli.help_file"))
    parser.add_argument(
        "--voice",
        type=_voice,
        nargs="?",
        const=VOICE_MENU,
        metavar=phrase("cli.metavar_voice"),
        help=phrase("cli.help_voice"),
    )
    # Прежнее имя того же флага: ломать чужие пальцы и историю оболочки незачем.
    parser.add_argument(
        "--audio",
        type=_voice,
        nargs="?",
        const=VOICE_MENU,
        dest="voice",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        FROM_START_FLAG,
        dest="from_start",
        action="store_true",
        help=phrase("cli.help_new"),
    )
    parser.add_argument("--dry", action="store_true", help=phrase("cli.help_dry"))
    parser.add_argument(
        "--since", metavar=phrase("cli.metavar_since"), help=phrase("cli.help_since")
    )
    parser.add_argument("--play-key", metavar="KEY", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"torrcast {__version__}")
    return Args(**vars(parser.parse_args(argv)))
