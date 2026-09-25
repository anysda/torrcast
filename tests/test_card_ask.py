from __future__ import annotations

from web.card_ask import NO_ASK, CardAsk


def test_the_page_ask_is_read_from_the_query() -> None:
    asked = CardAsk.of(
        {
            "query": "рик и морти",
            "shown": "Rick and Morty",
            "lang": "ru",
            "season": "2",
            "voices": "1",
        }
    )

    assert asked == CardAsk("рик и морти", "ru", 2, True, "Rick and Morty")


def test_a_garbage_season_tab_leaves_the_choice_to_the_first_tab() -> None:
    for tab in ("0", "41", "-1", "два", ""):
        assert CardAsk.of({"query": "q", "season": tab}).season is None, tab
    assert CardAsk.of({"query": "q", "season": "40"}).season == 40


def test_tracks_are_waited_for_only_when_asked() -> None:
    assert not CardAsk.of({"query": "q", "voices": "0"}).voices
    assert CardAsk.of({}) == NO_ASK
