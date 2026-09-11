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


def test_the_page_speaks_russian_when_asked() -> None:
    assert _said({"lang": "ru"})["web.shelf.new"] == "Новинки"


def test_an_unknown_language_falls_back_to_english_and_not_to_emptiness() -> None:
    assert _said({"lang": "de"})["web.shelf.new"] == "New"


def test_both_languages_hold_the_very_same_keys() -> None:
    """Ключ, забытый в одном языке, - это надпись, пропавшая со страницы при переключении."""
    assert _said({}).keys() == _said({"lang": "ru"}).keys()


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


def test_numbered_words_hold_the_forms_people_read() -> None:
    english, russian = _said({}), _said({"lang": "ru"})
    cases = {
        "web.search.searching": (
            ("Searching {n} source…", "Searching {n} sources…"),
            ("Ищем в {n} источнике…", "Ищем в {n} источниках…", "Ищем в {n} источниках…"),
        ),
        "web.search.result": (
            ("{n} result", "{n} results"),
            ("{n} находка", "{n} находки", "{n} находок"),
        ),
        "web.search.source": (
            ("{n} source", "{n} sources"),
            ("{n} источник", "{n} источника", "{n} источников"),
        ),
        "web.detail.release": (
            ("{n} release", "{n} releases"),
            ("{n} раздача", "{n} раздачи", "{n} раздач"),
        ),
        "web.detail.source_from": (
            ("{n} source", "{n} sources"),
            ("{n} источника", "{n} источников", "{n} источников"),
        ),
        "web.detail.seasons": (
            ("{n} season", "{n} seasons"),
            ("{n} сезон", "{n} сезона", "{n} сезонов"),
        ),
    }
    for key, ((en_one, en_other), (ru_one, ru_few, ru_many)) in cases.items():
        assert (
            english[key + ".one"],
            english[key + ".few"],
            english[key + ".many"],
            english[key + ".other"],
        ) == (en_one, en_other, en_other, en_other)
        assert (
            russian[key + ".one"],
            russian[key + ".few"],
            russian[key + ".many"],
            russian[key + ".other"],
        ) == (ru_one, ru_few, ru_many, ru_many)


def test_the_dictionary_travels_as_readable_utf8_and_not_as_escapes() -> None:
    answer = phrases(Request("GET", "/api/phrases", {"lang": "ru"}, {}))

    assert "Новинки".encode() in answer.body
