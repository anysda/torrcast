"""Английский каталог кластера разговора с приёмником: он же умолчание, он же запасной."""

from __future__ import annotations

import re

from torrcast.domain.catalogs.chromecast_talk.en import en as english

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def test_english_catalog_holds_no_russian() -> None:
    russian = [key for key, line in english().items() if _CYRILLIC.search(line)]
    assert russian == []


def test_every_key_names_its_cluster() -> None:
    stray = [key for key in english() if not key.startswith("chromecast_talk.")]
    assert stray == []
    assert english()["chromecast_talk.refused_crashed"] == "crashed: {reason}"


def test_the_three_refusal_words_stay_three() -> None:
    refused = [key for key in english() if key.startswith("chromecast_talk.refused_")]
    words = {english()[key].split(":")[0] for key in refused}
    assert words == {"refused", "crashed", "not taken"}
