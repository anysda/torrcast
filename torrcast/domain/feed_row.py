"""Правило FeedRow; используют модели и фасады разбора имён."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from torrcast.domain.raw_result import RawResult


@dataclass(frozen=True, slots=True)
class FeedRow:
    """Одна строка ленты последних раздач: сырые поля плюс время первой раздачи.

    ``RawResult`` даты не несёт (её не спрашивает никто, кроме этой ленты), а заводить
    поле в предмете, которым пользуется весь каталог, ради одной полки - расширять
    чужой файл ради своего угла. Дата и хэш едут рядом, а после кластеризации в картины
    находятся обратно по хэшу из ``magnet`` (:func:`torrcast.domain.magnet_hash.magnet_hash`).
    """

    raw: RawResult
    published: datetime


__all__ = ["FeedRow"]
