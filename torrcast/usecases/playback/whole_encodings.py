"""Завод решения о СПЛОШНОМ перекоде файла: пресет, битрейт и кадр одним значением.

Кладёт его композиционный корень (:mod:`torrcast.runtime.wire`) под именем
``whole_encode``. Живёт он в медиатракте, а не у показа, потому что спрашивают о нём
трое: сам показ, сетка прогрева и щупы замера.
"""

from __future__ import annotations

from typing import Protocol

from torrcast.ports.recode.encoding import Encoding


class WholeEncodings(Protocol):
    """Чем показ решает, как перекодировать весь файл - и ничего сверх того."""

    def __call__(
        self,
        mbit: float,
        video_mbit: float = 0.0,
        frame: int = 0,
        ceiling: int = 0,
        hdr: bool = False,
    ) -> Encoding:
        """Одно решение на весь показ; тем же обязан кодировать прогрев."""
