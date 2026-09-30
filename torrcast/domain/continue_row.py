"""Ряд «Продолжить» и сколько его первых записей служба держит тёплыми."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from torrcast.domain.entry import Entry

#: Столько первых записей ряда греется до клика (:mod:`web.record_warm`) и столько же
#: сохраняет после показа кэш раздачи на диске службы
#: (:func:`torrcast.usecases.torrents._release_orphans`). Прогрев одной записи - это
#: карта, голова, начало ленты и 32 МБ у закладки: 40-60 МБ из роя и 5-20 с, у каждой
#: записи своя рука. Кэш показа у записи - до ``CacheSize`` службы (8 ГиБ по умолчанию),
#: поэтому число и есть потолок диска; раздачи прочих записей истории сносятся
#: (:mod:`web.record_sweep`).
WARM_ROW: Final = 3


def continue_row(entries: Mapping[str, Entry]) -> list[str]:
    """Ключи ряда «Продолжить», как его рисует главная: недосмотренные, свежая первой."""
    fresh = sorted(entries.items(), key=lambda kv: kv[1].updated, reverse=True)
    return [key for key, entry in fresh if not entry.watched]
