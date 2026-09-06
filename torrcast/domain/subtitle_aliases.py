"""Неоднозначный номер перед подзаголовком не становится псевдонимом."""

from __future__ import annotations

from collections.abc import Iterable

from torrcast.domain.numbered_subtitle import numbered_subtitle
from torrcast.domain.part_number import part_number
from torrcast.domain.slugify import slugify


def subtitle_aliases(names: Iterable[str]) -> dict[str, str]:
    """Общее имя допустимо лишь при одном номере: две части с одним хвостом не сливать."""
    reduced = {name: numbered_subtitle(name) for name in names}
    numbers: dict[str, set[int]] = {}
    for name, alias in reduced.items():
        if name != alias and (number := part_number(name.partition(":")[0])) is not None:
            numbers.setdefault(slugify(alias), set()).add(number)
    return {
        name: alias if len(numbers.get(slugify(alias), set())) <= 1 else name
        for name, alias in reduced.items()
    }


__all__ = ["subtitle_aliases"]
