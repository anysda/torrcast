"""Выжимка недельного следа: одна лента записей - в человеческий текст ``cast log``.

Разбор чистый: ни файлов, ни очереди - их держит сам след
(:mod:`torrcast.adapters.filesystem.trace_journal`). Ветки событий разведены по
разборщикам фаз, а сборка сеанса и стыки источника лежат рядом.
"""

from __future__ import annotations

from torrcast.domain.digest._seams import _seams as _seams
from torrcast.domain.digest.digest import digest as digest

__all__ = ["_seams", "digest"]
