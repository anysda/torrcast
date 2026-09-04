"""Названные флаги, которых путь показа не читает.
Зовёт их :func:`torrcast.cli.main.main` до того, как отдать работу команде.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from typing import Final

from torrcast.cli.parse_args import FROM_START_FLAG
from torrcast.domain.args import Args

#: Флаг на каждое поле :class:`Args`, которое называет человек. Полнота списка сверяется
#: с полями самого :class:`Args` зеркальным тестом: заведи флаг и не назови его тут - и
#: показ снова примет его молча.
_FLAG: Final[Mapping[str, str]] = {
    "tv": "--tv",
    "telegram": "-tg",
    "language": "--ru/--en",
    "release": "--release",
    "pick": "--pick",
    "menu": "--menu",
    "file": "--file",
    "voice": "--voice",
    "from_start": FROM_START_FLAG,
    "dry": "--dry",
    "since": "--since",
    "play_key": "--play-key",
    "upgrade": "--upgrade",
}

#: Что читает сам показ. ``language`` тут потому, что язык рядом с работой запоминает
#: точка входа (:func:`torrcast.cli.main.main`): для человека флаг понят и работы не
#: отменяет. ``telegram``, ``upgrade`` и ``play_key`` показом не бывают вовсе - каждый
#: уводит разбор в свою команду (:attr:`Args.command`), - и в ответе они не появятся.
_READ_BY_PLAY: Final = frozenset(
    {"language", "release", "pick", "menu", "file", "voice", "from_start", "dry"}
)

#: Умолчание поля и есть «флаг не назван»: у всех до одного оно ``None`` или ``False``.
_DEFAULT: Final[Mapping[str, object]] = {item.name: item.default for item in fields(Args)}


def stray_flags(args: Args) -> list[str]:
    """Флаги этого запуска, которых показ не читает, в порядке справки.

    Пустой ответ значит «показ понял всё названное», а не «флагов не было»: голый
    ``cast`` и ``cast --dry`` отвечают им одинаково, и путь «продолжи последнее»
    остаётся ровно прежним.
    """
    return [
        flag
        for name, flag in _FLAG.items()
        if name not in _READ_BY_PLAY and getattr(args, name) != _DEFAULT[name]
    ]
