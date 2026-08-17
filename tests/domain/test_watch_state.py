"""Правила состояния просмотра: что оно отвечает на запрос, показ и уборку."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState


def _state(**entries: Entry) -> WatchState:
    """Состояние из готовых записей: ключи задаются именем аргумента."""
    return WatchState({key.replace("__", ":"): entry for key, entry in entries.items()})


def test_the_question_finds_the_picture_it_named() -> None:
    """Запрос сверяется со slug'ом ключа: продолжается та картина, которую назвали."""
    state = _state(
        **{"movie__матрица__1999": Entry(title="Матрица", magnet="m", updated="2026-01-01")}
    )
    found = state.find("матрица")
    assert found is not None and found[0] == "movie:матрица:1999"


def test_a_series_answers_a_short_name() -> None:
    """Сериал зовут короче полного названия, и это законно - в отличие от фильма."""
    state = _state(
        **{
            "tv__киберпанк-бегущие-по-краю__2022": Entry(
                title="Киберпанк", magnet="m", kind="tv", updated="2026-01-01"
            )
        }
    )
    assert state.find("киберпанк") is not None


def test_the_freshest_record_is_the_one_status_shows() -> None:
    """`cast status` показывает свежайшую запись, а не первую попавшуюся."""
    state = _state(
        movie__a__2000=Entry(title="A", magnet="m", updated="2026-01-01"),
        movie__b__2001=Entry(title="B", magnet="m", updated="2026-02-02"),
    )
    latest = state.latest()
    assert latest is not None and latest[1].title == "B"


def test_only_a_written_hash_counts_as_held() -> None:
    """Держит раздачу тот, у кого записан хэш: по нему уборка и отличает чужое."""
    state = _state(
        movie__a__2000=Entry(title="A", magnet="m", torrent="abc"),
        movie__b__2001=Entry(title="B", magnet="m"),
    )
    assert state.held() == {"abc"}


def test_the_show_going_now_is_the_one_with_a_hash() -> None:
    """Идущий показ виден по тому же признаку, что и держание раздачи."""
    state = _state(movie__a__2000=Entry(title="A", magnet="m", torrent="abc", updated="2026-01-01"))
    showing = state.showing()
    assert showing is not None and showing[1].torrent == "abc"


def test_putting_a_record_stamps_it() -> None:
    """Запись кладётся со свежей меткой времени: по ней потом считается свежайшая."""
    state = WatchState()
    state.put("movie:a:2000", Entry(title="A", magnet="m"))
    assert state.entries["movie:a:2000"].updated

    state.drop("movie:a:2000")
    assert not state.entries
