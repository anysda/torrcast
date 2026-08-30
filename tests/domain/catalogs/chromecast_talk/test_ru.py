"""Парный сторож русского каталога: те же ключи и те же подстановки, что у английского."""

from __future__ import annotations

from string import Formatter

from torrcast.domain.catalogs.chromecast_talk.en import en as english
from torrcast.domain.catalogs.chromecast_talk.ru import ru as russian


def _values(line: str) -> set[str]:
    return {name for _text, name, _spec, _conv in Formatter().parse(line) if name}


def test_russian_holds_every_english_key() -> None:
    assert russian().keys() == english().keys()


def test_both_tongues_substitute_the_same_names() -> None:
    russian_names = {key: _values(line) for key, line in russian().items()}
    english_names = {key: _values(line) for key, line in english().items()}
    assert russian_names == english_names


def test_russian_lines_are_russian() -> None:
    dumb = [key for key, line in russian().items() if line == english()[key]]
    assert dumb == []


def test_the_three_refusal_words_stay_three() -> None:
    refused = [key for key in russian() if key.startswith("chromecast_talk.refused_")]
    words = {russian()[key].split(":")[0] for key in refused}
    assert words == {"нельзя", "упал", "не взял"}
