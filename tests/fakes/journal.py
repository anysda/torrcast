"""Лента, которая ничего не пишет, а только помнит названные ей события.

Ставится она на порт следа (:mod:`torrcast.ports.journal`), а не подменой укладки у
фонового писателя: зеркалу нужен ответ «что показ рассказал о себе», и спрашивать его
надо договором ленты. Как эти события ложатся в файл - вопрос самой ленты, и на него
отвечают её собственные зеркала (``tests/adapters/filesystem/trace_journal``).

Возвращает порт на место автоматическая фикстура ``_ports_restored``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from torrcast.ports.journal.silent import Silent

#: Одно пойманное событие: имя и поля ровно в том виде, в каком их назвал зовущий.
Call = tuple[str, dict[str, Any]]


@dataclass
class Tape(Silent):
    """Помнит названные события показа: подталкивание, повтор LOAD и перемотку."""

    calls: list[Call] = field(default_factory=list)

    def nudge(self, pos: float, to: float, hit: int, stuck: float, front: float) -> None:
        fields = {"pos": pos, "to": to, "hit": hit, "stuck": stuck, "front": front}
        self.calls.append(("nudge", fields))

    def reload(self, pos: float, tries: int, error: int | None = None) -> None:
        self.calls.append(("reload", {"pos": pos, "tries": tries, "error": error}))

    def seek(self, frm: float, to: float, wait: float | None, why: str = "") -> None:
        self.calls.append(("seek", {"frm": frm, "to": to, "wait": wait, "why": why}))

    def mark(self, name: str, **facts: Any) -> None:
        """Помеченное событие: имя ему даёт зовущий, по нему же его и спрашивают.

        Помнить их обязательно: молчащий отказ склейки виден только этой строкой, а
        «строки нет вовсе» - это семь минут разбора подвиса вслепую (TC-800).
        """
        self.calls.append((name, facts))

    def named(self, event: str) -> list[dict[str, Any]]:
        """Поля событий одного имени - по ним зеркала и сверяют рассказ показа."""
        return [fields for name, fields in self.calls if name == event]

    def events(self) -> list[str]:
        """Имена событий по порядку: чем показ отчитался и сколько раз."""
        return [name for name, _fields in self.calls]
