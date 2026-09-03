"""Найденная статья вместе с тем, чем сверяется её год; зовёт отбор статей постера."""

from __future__ import annotations

from typing import NamedTuple


class Dated(NamedTuple):
    """Английская статья и чем сверить её год: годы даром и сущность Wikidata на запас.

    ``years`` пусто - значит, статья про свой год не сказала ничего, и спрашивать
    придётся Wikidata по ``entity``. Это НЕ то же самое, что «год не тот».
    """

    page: str
    entity: str
    years: frozenset[int]
    kinds: frozenset[str] = frozenset()
