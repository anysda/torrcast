"""Дописывает второй источник в отметку паспорта; зовёт сценарий паспорта."""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import SOURCE_JOIN


def with_source(found: Origin, added: str) -> Origin:
    """Дописать второй источник: «wiki» + «map» = «wiki+map». Пустое и повтор не пишутся."""
    parts = [part for part in found.source.split(SOURCE_JOIN) if part]
    if not added or added in parts:
        return found
    return replace(found, source=SOURCE_JOIN.join([*parts, added]))
