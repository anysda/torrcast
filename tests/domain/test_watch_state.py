"""Правила состояния просмотра: что оно отвечает на запрос, показ и уборку."""

from __future__ import annotations

from tests.usecases.cast_command.world import entry
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


def test_a_series_with_a_single_episode_still_answers_its_short_name() -> None:
    """Сериал из одной серии - всё ещё сериал: число в его названии это сезон,
    а не часть франшизы, и короткое имя находит его закладку.
    """
    state = _state(
        **{
            "tv__кухня-6__2016": Entry(
                title="Кухня 6",
                magnet="m",
                kind="tv",
                query="кухня-6",
                season=6,
                episode=1,
                episodes=[[6, 1, 0]],
                updated="2026-01-01",
            )
        }
    )
    found = state.find("кухня")
    assert found is not None and found[0] == "tv:кухня-6:2016"


def test_a_film_written_as_a_series_stays_closed_to_the_franchise_name() -> None:
    """Осечка разбора оставила «Moana 2» записанной сериалом с одной серией s1e1:
    её двойка сезоном не является (запись стоит в s1), и имя франшизы ей не
    достаётся - достаётся только названный номер.
    """
    state = _state(
        **{
            "tv__moana-2__2024": Entry(
                title="Moana 2",
                magnet="m",
                kind="tv",
                query="моана-2",
                season=1,
                episode=1,
                episodes=[[1, 1, 1]],
                pos=100,
                updated="2026-01-01",
            )
        }
    )
    assert state.find("moana") is None
    found = state.find("моана 2")
    assert found is not None and found[0] == "tv:moana-2:2024"


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


def test_the_other_name_of_a_dated_picture_finds_its_bookmark() -> None:
    """The circle named the film by its original: the card still finds the saved place."""
    state = WatchState()
    state.put("movie:тачки:2006", entry(title="Тачки", original="Cars"))
    assert state.bookmark_key("movie:cars:2006") == "movie:тачки:2006"
    assert state.bookmark_key("movie:тачки:2006") == "movie:тачки:2006"


def test_another_year_or_two_namesakes_are_not_the_card_s_bookmark() -> None:
    """A remake of another year is another picture, and two candidates name nobody."""
    state = WatchState()
    state.put("movie:оно:1990", entry(title="Оно", original="It"))
    assert state.bookmark_key("movie:it:2017") is None
    state.put("movie:оно:2017", entry(title="Оно", original="It"))
    state.put("movie:это:2017", entry(title="Это", original="It"))
    assert state.bookmark_key("movie:it:2017") is None
    assert state.bookmark_key("movie:оно:2017") == "movie:оно:2017"


def test_without_a_year_only_the_own_key_answers() -> None:
    """One shared name does not tell two yearless pictures apart."""
    state = WatchState()
    state.put("tv:дом-house:0", entry(kind="tv", title="Дом", original="House"))
    state.put("movie:оно-it:0", entry(title="Оно", original="It"))
    assert state.bookmark_key("tv:дом:0") is None
    assert state.bookmark_key("movie:it:0") is None
    assert state.bookmark_key("tv:дом-house:0") == "tv:дом-house:0"
