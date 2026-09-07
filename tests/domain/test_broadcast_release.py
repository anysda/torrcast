"""Зеркало :mod:`torrcast.domain.broadcast_release`: спортивная трансляция по имени."""

import re

import pytest

import torrcast.domain.broadcast_release as broadcast_release
from torrcast.domain.broadcast_release import _is_broadcast_release


def test_a_football_broadcast_is_caught_by_its_heading() -> None:
    assert _is_broadcast_release(
        "Футбол. Чемпионат Англии 2026-2027. 3-й тур. Арсенал - Челси [06.09] (2026) HDTV 720р"
    )


def test_a_racing_and_a_fight_night_are_caught_too() -> None:
    assert _is_broadcast_release(
        "Формула 1. S2026. Этап 13. Гран-при Италии. Гонка [06.09] (2026) HDTV 720р"
    )
    assert _is_broadcast_release(
        "Смешанные единоборства. UFC Fight Night 287: Hooker vs. Parnasse [05.09] (2026) WEBRip"
    )


def test_english_sport_programme_headings_are_caught() -> None:
    assert _is_broadcast_release("Match Of The Day")
    assert _is_broadcast_release("All Elite Wrestling Collision")
    assert _is_broadcast_release("AEW Dynamite 2026.09.09 1080p WEB h264-HEEL")
    assert _is_broadcast_release("WWE Monday Night Raw 2026.09.07 1080p WEB h264-HEEL")
    assert _is_broadcast_release("WWE Friday Night SmackDown 2026.09.11 1080p WEB h264-HEEL")
    assert _is_broadcast_release("UFC Fight Night 267 2026.09.06 1080p WEB-DL")
    assert _is_broadcast_release("NFL RedZone 2026 Week 1 1080p WEB h264-FUM")


def test_removing_english_headings_would_let_them_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отрицательная проба: без добавленной формы шоу снова проходят как картины."""
    monkeypatch.setattr(broadcast_release, "_ENGLISH_BROADCAST_RE", re.compile(r"$^"))
    names = [
        "AEW Dynamite 2026.09.09 1080p WEB h264-HEEL",
        "WWE Monday Night Raw 2026.09.07 1080p WEB h264-HEEL",
        "WWE Friday Night SmackDown 2026.09.11 1080p WEB h264-HEEL",
        "UFC Fight Night 267 2026.09.06 1080p WEB-DL",
        "NFL RedZone 2026 Week 1 1080p WEB h264-FUM",
    ]
    assert not any(broadcast_release._is_broadcast_release(name) for name in names)


def test_a_picture_named_by_the_same_word_stays() -> None:
    """Слово есть, заголовочной точки нет - это кино, а не трансляция."""
    assert not _is_broadcast_release("Бокс (2010) BDRip")
    assert not _is_broadcast_release("Матч-реванш. Футбол моей юности (1980) DVDRip")


def test_an_ordinary_release_is_not_flagged() -> None:
    assert not _is_broadcast_release("Брат. Часть 2 (2000) BDRip")
    assert not _is_broadcast_release("Интерстеллар / Interstellar (2014) BDRemux 1080p")
    assert not _is_broadcast_release("The Match (2020) WEB-DL 1080p")
    assert not _is_broadcast_release("Collision (2013) BDRip")
    assert not _is_broadcast_release("Year of the Scab (2017) 1080p WEB-DL")
