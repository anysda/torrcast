"""Индикатор, которого нет: прогон без композиционного корня ничего не рисует."""

from __future__ import annotations

from types import TracebackType


class Quiet:
    """Умолчание порта индикатора: принимает фазы и заметки и не печатает ничего."""

    def phase(self, text: str) -> None:
        return None

    def note(self, text: str) -> None:
        return None

    def stop(self) -> None:
        return None

    def __enter__(self) -> Quiet:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        return None
