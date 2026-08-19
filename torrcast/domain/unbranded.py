"""Правило unbranded; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data.data_3 import _CHANNEL_RE


def _unbranded(title: str) -> str:
    return _CHANNEL_RE.sub("", title.strip(), count=1)


__all__ = ["_unbranded"]
