"""Пустой круг, сорванный сетью: «не знаю», а не «ничего не нашлось»."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.domain.torrcast_error import TorrcastError
    from torrcast.usecases.select.plan import Plan


class TornCircle(list["Plan"]):
    """Пуст, как отказ (ждущие не переспрашивают сеть до срока), но несёт сорвавшую ошибку."""

    def __init__(self, error: TorrcastError) -> None:
        super().__init__()
        self.error = error


__all__ = ["TornCircle"]
