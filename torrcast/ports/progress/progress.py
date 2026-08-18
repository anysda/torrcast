"""Показывает человеку, что сценарий делает прямо сейчас, и что он уже решил.

Две строки на весь показ: бегущая фаза («поиск «моана»… 3.1 с») и заметки, которые
остаются на экране насовсем. Кто их рисует - терминал, файл или никто, - решает
композиционный корень (:mod:`torrcast.runtime.wire`); до его слова индикатор молчит.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol


class Progress(Protocol):
    """Что сценариям нужно от индикатора - и ничего сверх того."""

    def phase(self, text: str) -> None:
        """Назвать текущую фазу; пусто - фаза кончилась."""

    def note(self, text: str) -> None:
        """Оставить на экране строку, которая переживёт бегущую фазу."""

    def stop(self) -> None:
        """Убрать бегущую строку: дальше печатает кто-то другой."""

    def __enter__(self) -> Progress: ...

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None: ...
