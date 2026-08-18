"""Сырая выдача каталога раздач: её склейка в один список и разбор в релизы.

Считают то и другое в адаптере (:mod:`torrcast.adapters.prowlarr`) - рядом с тем, кто
строки привёз, - а слою сценариев адаптер не назвать: правило слоёв такой импорт
запрещает. Отсюда порт: сценарий добора зовёт склейку и разбор по договору, а кто их
считает, решает композиционный корень.

Сама строка выдачи (:class:`~torrcast.domain.raw_result.RawResult`) при этом лежит в
домене, и договор называет её своим именем. Пустого договора-возчика тут было бы мало:
строки ходят СПИСКАМИ, а список в типах неизменен - ``list[RawResult]`` под ``list``
договора о строке не подставляется, даже когда сама строка договору отвечает.
"""

from __future__ import annotations

from typing import Protocol

from torrcast.domain.raw_result import RawResult
from torrcast.domain.release import Release


class TorrentCatalogue(Protocol):
    """Что сценарию добора нужно от сырой выдачи каталога - и ничего сверх того."""

    def merge(self, *batches: list[RawResult]) -> list[RawResult]:
        """Склеить выдачи нескольких запросов, оставив каждую раздачу один раз."""

    def to_releases(self, rows: list[RawResult]) -> list[Release]:
        """Разобрать сырые строки в релизы: имя, размер, сиды, magnet."""
