"""Запрос для показа, когда зритель не назвал картину."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.watch_state import WatchState


def _default_query(state: WatchState) -> str:
    """Назвать последний игравший сериал или «Тачки» для первого запуска."""
    latest = state.latest_serial()
    if latest is None:
        return phrase("cmd_play.first_show")
    return latest[1].query or latest[1].title
