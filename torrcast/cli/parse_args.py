"""Разбор ``argv`` по контракту ``cast``: единственное место, где живёт argparse.
Зовёт его :func:`torrcast.cli.main.main`, результат читают команды пакета
:mod:`torrcast.cli`.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from torrcast.domain.args import Args
from torrcast.domain.rank_settings import VOICE_MENU
from torrcast.domain.version import __version__

FROM_START_FLAG, FROM_START_HELP = "--new", "та же раздача, файл и дорожка с начала"
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
    """Разобрать argv по контракту CLI."""
    about = "torrcast - найти релиз и кастить его на ТВ без скачивания"
    parser = argparse.ArgumentParser(prog="cast", description=about, allow_abbrev=False)
    parser.add_argument("query", nargs="*", help="название, либо stop / status")
    parser.add_argument(
        "--tv",
        nargs="?",
        const=TV_MENU,
        metavar="IP",
        help="настройка ТВ: без адреса - найти приёмники в сети и выбрать из списка",
    )
    parser.add_argument(
        "-tg",
        dest="telegram",
        action="store_true",
        help="открыть меню настройки Telegram-бота",
    )
    # Язык - настройка, а не режим запуска: флаг ЗАПОМИНАЕТСЯ, и следующий `cast` уже
    # говорит на нём же. Умолчание тут `None`, а не "en": «язык не назван» и «назван
    # английский» - разные ответы, и первый обязан взять язык из настройки.
    tongue = parser.add_mutually_exclusive_group()
    tongue.add_argument(
        "--ru",
        dest="language",
        action="store_const",
        const="ru",
        help="перейти на русский и запомнить выбор",
    )
    tongue.add_argument(
        "--en",
        dest="language",
        action="store_const",
        const="en",
        help="перейти на английский и запомнить выбор",
    )
    # Номер релиза имеет смысл только вместе с запросом и выбранной картиной: другой
    # запрос - другой список, а у каждой картины в нём - свои номера (TC-446).
    parser.add_argument(
        "--release",
        type=int,
        metavar="N",
        help="отладка: релиз N выбранной картины; номера - из cast releases с тем же запросом",
    )
    parser.add_argument("--pick", type=int, metavar="N", help="картина N из меню, без вопроса")
    # Закладка отвечает на «где я остановился», а меню - на «что играть»: этой ручкой
    # спрашивают второе, и сохранённое место у неё дороги не занимает.
    parser.add_argument(
        "--menu",
        action="store_true",
        help="показать список картин и спросить, а не включать самому",
    )
    parser.add_argument("--file", type=int, metavar="N", help="отладка: взять файл N раздачи")
    parser.add_argument(
        "--voice",
        type=_voice,
        nargs="?",
        const=VOICE_MENU,
        metavar="N|СТУДИЯ",
        help="озвучка: номер или студия - взять и запомнить, без значения - меню",
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
        FROM_START_FLAG, dest="from_start", action="store_true", help=FROM_START_HELP
    )
    parser.add_argument("--dry", action="store_true", help="весь резолв без каста")
    parser.add_argument(
        "--since", metavar="СРОК", help="cast log: с какого момента (2d / 12h / 30m / ГГГГ-ММ-ДД)"
    )
    parser.add_argument("--play-key", metavar="KEY", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"torrcast {__version__}")
    return Args(**vars(parser.parse_args(argv)))
