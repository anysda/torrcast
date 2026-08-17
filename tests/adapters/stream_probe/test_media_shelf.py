"""Полка паспортов: где лежит запись, что в ней хранится и почему старую версию не берут."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from torrcast.adapters.stream_probe.media_shelf import (
    _MEDIA_VERSION,
    _keep_media,
    _media_cache,
    _read_media,
)
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media

if TYPE_CHECKING:
    from pathlib import Path

_PASSPORT = Media(
    duration=3600.0,
    tracks=(AudioTrack(0, "rus", "дубляж", "eac3", 6),),
    video="hevc",
    profile="Main 10",
    pix_fmt="yuv420p10le",
    color_trc="smpte2084",
    field_order="progressive",
    height=1080,
    width=1920,
    video_bps=14_333_020.0,
)


def test_the_key_is_the_stream_address_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """В адресе потока лежат хэш раздачи и номер файла - ровно то, что задаёт содержимое."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))

    same = _media_cache("http://torr/stream/hash-1/2")
    again = _media_cache("http://torr/stream/hash-1/2")
    other = _media_cache("http://torr/stream/hash-1/3")

    assert same == again and same != other
    assert same.parent.name == "probe" and same.suffix == ".json"


def test_a_passport_survives_the_shelf_field_by_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Следующая серия узнаёт длительность отсюда - и обязана узнать её даже без сети."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    cache = _media_cache("http://torr/stream/hash-1/2")

    _keep_media(cache, _PASSPORT)

    assert _read_media(cache) == _PASSPORT


def test_a_record_of_an_older_format_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Прежние паспорта молчат про формат кадра ровно так же, как молчал старый ffprobe.

    Прими такой за правду - и показ уехал бы копией на приёмник, который её не декодирует.
    Цена отказа - один ffprobe на файл; цена доверия - вечная петля на экране.
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    cache = _media_cache("http://torr/stream/hash-1/2")
    _keep_media(cache, _PASSPORT)
    saved = json.loads(cache.read_text("utf-8"))
    saved["v"] = _MEDIA_VERSION - 1
    cache.write_text(json.dumps(saved), encoding="utf-8")

    assert _read_media(cache) is None


def test_a_half_read_header_never_becomes_a_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Паспорт без длительности и дорожек - это не паспорт, а недочитанный заголовок.

    Положи такой в кэш - и осечка одного запуска станет вечной."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    cache = _media_cache("http://torr/stream/hash-1/2")

    _keep_media(cache, Media(duration=0.0, tracks=(), video="h264"))
    _keep_media(cache, Media(duration=3600.0, tracks=(), video="h264"))

    assert not cache.exists()


def test_a_broken_record_is_answered_by_none_not_by_a_fall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Кэш - ускорение, а не источник правды, и показ обязан идти и без него."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    cache = _media_cache("http://torr/stream/hash-1/2")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("не json вовсе", encoding="utf-8")

    assert _read_media(cache) is None
    assert _read_media(cache.parent / "нет.json") is None


def test_reading_a_passport_marks_the_shelf_as_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Полка живёт по времени обращения, и чтение обязано это время двигать."""
    import os

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    cache = _media_cache("http://torr/stream/hash-1/2")
    _keep_media(cache, _PASSPORT)
    os.utime(cache, (1, 1))

    assert _read_media(cache) is not None
    assert cache.stat().st_mtime > 1, "запись отмечена спрошенной"
