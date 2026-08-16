"""Правило wire query; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data import _GLUE


def wire_query(query: str) -> str:
    return _GLUE.sub(" ", query)


__all__ = ["wire_query"]
