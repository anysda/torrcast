"""Индикатор, которого нет: прогон без композиционного корня ничего не рисует."""

from __future__ import annotations

from types import TracebackType


class Quiet:
    """Умолчание порта индикатора: принимает фазы и заметки и не печатает ничего.

    Сказанное дальше не идёт никуда, а имена стоят как в договоре
    (:class:`Progress`): по ним индикатор и подставляется вместо этого.
    """

    def phase(self, text: str) -> None:
        """Фаза принята и не нарисована."""

    def note(self, text: str) -> None:
        """Заметка принята и не нарисована."""

    def stop(self) -> None:
        """Гасить нечего: бегущей строки не было."""

    def __enter__(self) -> Quiet:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        return None
