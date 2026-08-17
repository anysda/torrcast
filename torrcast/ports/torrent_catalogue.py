"""Сырая выдача каталога раздач: её склейка в один список и разбор в релизы.

Сама выдача - строки индексеров и клиент, который их привёз, - живёт в адаптере
:mod:`torrcast.adapters.prowlarr`, а слою сценариев адаптер не назвать: правило слоёв
такой импорт запрещает. Отсюда порт: сценарий добора зовёт склейку и разбор по
договору, а кто их считает, решает фасад :mod:`torrcast.reinforce`.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeAlias

from torrcast.domain.release import Release

#: Строка сырой выдачи индексера
#: (:class:`~torrcast.adapters.prowlarr.raw_result.RawResult`). Сценарий добора
#: её НЕ ЧИТАЕТ - он только перекладывает строки между склейкой и разбором и отдаёт
#: их дальше, - поэтому полей тут не названо ни одного: всё, что он о строке знает,
#: это что она приехала из каталога.
RawRow: TypeAlias = Any

#: Клиент индексеров (:class:`~torrcast.adapters.prowlarr.prowlarr.Prowlarr`): один на
#: весь поиск вместе с доборами, со своим бюджетом и своим счётом молчунов. Сценарий и его не
#: спрашивает - он передаёт его кругу поиска (:func:`torrcast.usecases.discover._ask`)
#: и охраннику остатка цели (:func:`torrcast.usecases.discover._no_budget`), а договор
#: с ним держат они.
IndexerClient: TypeAlias = Any


class TorrentCatalogue(Protocol):
    """Что сценарию добора нужно от сырой выдачи каталога - и ничего сверх того."""

    def merge(self, *batches: list[RawRow]) -> list[RawRow]:
        """Склеить выдачи нескольких запросов, оставив каждую раздачу один раз."""

    def to_releases(self, rows: list[RawRow]) -> list[Release]:
        """Разобрать сырые строки в релизы: имя, размер, сиды, magnet."""
