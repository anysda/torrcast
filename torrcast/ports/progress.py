"""Показывает человеку, что сценарий делает прямо сейчас, и что он уже решил.

Две строки на весь показ: бегущая фаза («поиск «моана»… 3.1 с») и заметки, которые
остаются на экране насовсем. Кто их рисует - терминал, файл или никто, - решает
композиционный корень (:mod:`torrcast.runtime.wire`); до его слова индикатор молчит.
"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Any, Protocol


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


class _Quiet:
    """Индикатор, которого нет: прогон без корня ничего не рисует."""

    def phase(self, text: str) -> None:
        return None

    def note(self, text: str) -> None:
        return None

    def stop(self) -> None:
        return None

    def __enter__(self) -> _Quiet:
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None


_factory: Callable[[], Progress] = _Quiet


def progress() -> Progress:
    """Новый индикатор: по одному на фазу работы, а не один на процесс."""
    return _factory()


def factory() -> Callable[[], Progress]:
    """Чем сейчас рисуется ход: нужно тому, кто ставит своё и обязан вернуть чужое."""
    return _factory


def install(factory: Callable[[], Progress]) -> None:
    """Назначить, чем показывать ход. Зовёт это композиционный корень и тесты."""
    global _factory
    _factory = factory
