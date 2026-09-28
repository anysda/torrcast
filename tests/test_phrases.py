"""Словарь надписей страницы."""

from __future__ import annotations

import json

from web.answer import JSON
from web.phrases import phrases
from web.request import Request


def _said(query: dict[str, str]) -> dict[str, str]:
    answer = phrases(Request("GET", "/api/phrases", query, {}))
    assert answer.code == 200
    assert answer.kind == JSON
    parsed: dict[str, str] = json.loads(answer.body)
    return parsed


def test_the_page_speaks_english_when_no_language_is_asked() -> None:
    assert _said({})["web.shelf.new"] == "New"


def test_the_page_stays_english_when_russian_is_asked() -> None:
    assert _said({"lang": "ru"})["web.shelf.new"] == "New"


def test_an_unknown_language_falls_back_to_english_and_not_to_emptiness() -> None:
    assert _said({"lang": "de"})["web.shelf.new"] == "New"


def test_language_arguments_do_not_change_any_page_word() -> None:
    """Страница не получает русский словарь даже с явным старым доводом."""
    assert _said({}) == _said({"lang": "ru"})


def test_every_key_belongs_to_the_page() -> None:
    stray = [key for key in _said({}) if not key.startswith("web.")]

    assert stray == []


def test_the_words_the_handoff_screens_need_are_all_here() -> None:
    said = _said({})

    assert said["web.search.placeholder"] == "What are we watching?"
    assert said["web.shelf.continue_watching"] == "Continue watching"
    assert said["web.shelf.empty"] == "Nothing here yet"
    assert said["web.search.empty"] == "Nothing for you"
    assert said["web.player.lost"] == "Stream lost"
    assert said["web.player.next_in"] == "Next episode in {n}"
    assert said["web.detail.voice_fallback_note"] == "No Russian voice - playing the original"
    assert said["web.detail.season_absent"] == "No episodes"
    assert said["web.player.waiting_player"] == "waiting for the player"


def test_numbered_words_hold_the_forms_people_read() -> None:
    english = _said({})
    cases = {
        "web.search.searching": ("Searching {n} source…", "Searching {n} sources…"),
        "web.search.result": ("{n} result", "{n} results"),
        "web.search.source": ("{n} source", "{n} sources"),
        "web.detail.release": ("{n} release", "{n} releases"),
        "web.detail.source_from": ("{n} source", "{n} sources"),
        "web.detail.seasons": ("{n} season", "{n} seasons"),
    }
    for key, (en_one, en_other) in cases.items():
        assert (
            english[key + ".one"],
            english[key + ".few"],
            english[key + ".many"],
            english[key + ".other"],
        ) == (en_one, en_other, en_other, en_other)


def test_the_dictionary_travels_as_readable_utf8_and_not_as_escapes() -> None:
    answer = phrases(Request("GET", "/api/phrases", {"lang": "ru"}, {}))

    assert b"New" in answer.body
