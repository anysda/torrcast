"""Английский каталог кластера разбора коробки: он же умолчание, он же запасной.

Кириллица в нём - не опечатка, а невыполненный перевод: запасной каталог отвечает всем,
у кого языка нет вовсе, и русская строка оттуда уехала бы англоязычному человеку.
"""

from __future__ import annotations

import re

from torrcast.domain.catalogs.frames.en import en as english

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def test_english_catalog_holds_no_russian() -> None:
    russian = [key for key, line in english().items() if _CYRILLIC.search(line)]
    assert russian == []


def test_every_key_names_its_cluster() -> None:
    stray = [key for key in english() if not key.startswith("frames.")]
    assert stray == []
    assert english()["frames.mp4_no_video_trak"] == "the mp4 has no video track"
    assert english()["frames.unknown_container"] == (
        "not an mkv and not an mp4: nowhere to get a keyframe map from"
    )


def test_the_names_of_the_boxes_are_never_translated() -> None:
    """Имена боксов и элементов - слова формата, а не надписи: они одинаковы на всех языках.

    Строку эту человек несёт в поиск как есть, и переведённый ``stbl`` увёл бы его
    от единственного места, где написано, чего файлу не хватает.
    """
    for key, box in (
        ("frames.mp4_no_stbl", "stbl"),
        ("frames.mp4_no_mdhd", "mdhd"),
        ("frames.mp4_no_stts", "stts"),
        ("frames.mp4_no_moov", "moov"),
        ("frames.mkv_no_cues", "Cues"),
        ("frames.mkv_no_segment", "Segment"),
    ):
        assert box in english()[key], key
