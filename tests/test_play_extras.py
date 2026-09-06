"""Разбор новых полей ``POST /api/play``: имя озвучки, серия и «сначала»."""

from __future__ import annotations

from hass.play_extras import play_extras


def test_an_old_call_without_any_new_field_asks_for_nothing_extra() -> None:
    extras = play_extras({"query": "интерстеллар"})

    assert extras == {"from_start": False}


def test_a_named_voice_travels_through() -> None:
    extras = play_extras({"query": "q", "voice": "LostFilm"})

    assert extras == {"from_start": False, "voice": "LostFilm"}


def test_a_non_string_voice_is_refused() -> None:
    assert play_extras({"voice": 5}) == "bad_voice"


def test_season_and_episode_travel_through_together() -> None:
    extras = play_extras({"season": 1, "episode": 4})

    assert extras == {"from_start": False, "season": 1, "episode": 4}


def test_a_season_without_an_episode_is_refused() -> None:
    assert play_extras({"season": 1}) == "bad_episode"


def test_an_episode_without_a_season_is_refused() -> None:
    assert play_extras({"episode": 1}) == "bad_episode"


def test_a_zero_episode_is_refused() -> None:
    assert play_extras({"season": 1, "episode": 0}) == "bad_episode"


def test_a_boolean_episode_is_refused_even_though_it_is_an_int_in_python() -> None:
    assert play_extras({"season": 1, "episode": True}) == "bad_episode"


def test_from_start_travels_through() -> None:
    extras = play_extras({"from_start": True})

    assert extras == {"from_start": True}


def test_a_non_boolean_from_start_is_refused() -> None:
    assert play_extras({"from_start": "yes"}) == "bad_from_start"


def test_the_result_carries_every_field_the_card_sent() -> None:
    extras = play_extras({"voice": "LostFilm", "season": 1, "episode": 2})

    assert extras == {"from_start": False, "voice": "LostFilm", "season": 1, "episode": 2}
