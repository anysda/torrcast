"""Тип картины в разобранной раздаче; используют модели и правила каталога."""

from __future__ import annotations

from typing import Literal

Kind = Literal["movie", "tv", "other"]

__all__ = ["Kind"]
