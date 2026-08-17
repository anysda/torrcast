"""Поля записи ``play/offline``: источник перестал читаться.

Зовёт её показ, читает разбор ``cast log``."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def offline(why: str, asked: bool = False) -> None:
    """Источник перестал читаться: чем это объясняется и спрашивали ли самого источника.

    ``asked`` - правда ли причину назвал сам источник (:meth:`torrcast.stream.Origin.trouble`),
    а не догадка по мёртвому прогону упаковки. Разница существенная: «упаковка оборвалась»
    и «служба раздач не отвечает» выглядят в показе одинаково, а значат разное, и в следе
    это должно быть видно без гадания.
    """
    emit("play", "offline", why=why, asked=asked)
