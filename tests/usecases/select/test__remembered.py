"""Зеркало памяти озвучки: под каким ключом её ищут и чем добирают."""

from __future__ import annotations

from tests.usecases.select.world import entry
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.select._remembered import _remembered


def test_the_canonical_key_of_the_picture_is_where_the_voice_is_looked_for() -> None:
    """Под этим ключом показ запись и пишет - с него память и спрашивают."""
    state = WatchState()
    state.put("movie:кино:1999", entry(voice="Дубляж"))

    assert _remembered(state, "movie:кино:1999", None) == "Дубляж"


def test_a_record_found_by_the_text_of_the_query_is_the_spare() -> None:
    """У одной картины лежат записи разных запросов - память не зависит от их слов."""
    found = ("моана", entry(voice="Многоголосый"))

    assert _remembered(WatchState(), "movie:кино:1999", found) == "Многоголосый"


def test_without_any_record_the_memory_is_silence() -> None:
    """Записи нет - озвучку выберет обычный путь, по дорожкам потока."""
    assert _remembered(WatchState(), "movie:кино:1999", None) == ""
