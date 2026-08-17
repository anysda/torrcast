"""Вычёркивает источник, чей вклад в паспорт не попал; зовёт сценарий паспорта."""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import SOURCE_JOIN


def without_source(found: Origin, dropped: str) -> Origin:
    """Вычеркнуть источник, который в отданный паспорт так и не попал.

    Отметка описывает ОТДАННЫЙ ответ, а не путь, которым его собирали: источник, чей вклад
    по дороге отбросили, в ней остаться не вправе - иначе счёт припишет ему чужую заслугу.
    Последний оставшийся источник не вычёркивается: ответ откуда-то всё же взялся.
    """
    parts = [part for part in found.source.split(SOURCE_JOIN) if part]
    left = [part for part in parts if part != dropped]
    if not left or len(left) == len(parts):
        return found
    return replace(found, source=SOURCE_JOIN.join(left))
