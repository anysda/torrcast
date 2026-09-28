"""Индикатор отбора карточки, который выходит из отбора, когда её прогрев сняли.

Заводит его прогрев карточки (:meth:`web.card_warm.CardWarm.progress`), и только он.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.ports.progress.progress import Progress


class _StoppedError(Exception):
    """Отбор карточки снят: карточка ушла или стенд забирает показ."""


@dataclass(eq=False)
class CardProgress:
    """Индикатор отбора карточки: снятый прогрев выходит из отбора на следующей фазе."""

    inner: Progress
    halt: threading.Event

    #: Чем выходит снятый отбор карточки.
    stopped = _StoppedError

    def phase(self, text: str) -> None:
        if self.halt.is_set():
            raise _StoppedError
        self.inner.phase(text)

    def note(self, text: str) -> None:
        self.inner.note(text)

    def stop(self) -> None:
        self.inner.stop()

    def __enter__(self) -> CardProgress:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        return None
