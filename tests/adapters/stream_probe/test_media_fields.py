"""Вес видеодорожки и звуковая дорожка: три источника битрейта по убыванию надёжности."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.stream_probe.media_fields import _track, _video_bps


def test_the_mkvmerge_tag_is_believed_first() -> None:
    """Вес дорожки в голову mkv пишет mkvmerge - он есть у всех обычных релизов."""
    stream: dict[str, Any] = {"tags": {"BPS": "14333020"}, "bit_rate": "1"}

    assert _video_bps(stream, duration=3600.0) == 14_333_020.0


def test_the_language_suffix_of_the_tag_is_not_known_in_advance() -> None:
    """Mkvmerge пишет вес то как ``BPS``, то как ``BPS-eng``/``BPS-rus``."""
    assert _video_bps({"tags": {"bps-rus": "14096894"}}, 3600.0) == 14_096_894.0


def test_a_stream_field_answers_where_there_are_no_tags_at_all() -> None:
    """Mp4 и WEB-DL тегов mkvmerge не несут вовсе, а ``bit_rate`` у них есть."""
    assert _video_bps({"bit_rate": "8000000"}, 3600.0) == 8_000_000.0


def test_the_bytes_are_divided_by_the_length_as_a_last_resort() -> None:
    """Бывает, что mkvmerge написал вес дорожки, но не её битрейт."""
    stream: dict[str, Any] = {"tags": {"NUMBER_OF_BYTES-rus": str(3600 * 1_000_000)}}

    assert _video_bps(stream, duration=3600.0) == 8_000_000.0
    assert _video_bps(stream, duration=0.0) == 0.0, "без длительности делить не на что"


def test_nothing_found_is_an_honest_zero() -> None:
    """Профиль тяжести честно возвращается к слепой калибровке по первым сегментам."""
    assert _video_bps({}, 3600.0) == 0.0
    assert _video_bps({"tags": "не словарь", "bit_rate": "нечисло"}, 3600.0) == 0.0


def test_a_track_keeps_the_names_the_voice_menu_shows() -> None:
    """Меню озвучек показывает язык и название дорожки, а выбор считает каналы."""
    track = _track(
        2, {"codec_name": "eac3", "channels": "6", "tags": {"language": "rus", "title": "дубляж"}}
    )

    assert (track.index, track.language, track.title) == (2, "rus", "дубляж")
    assert (track.codec, track.channels) == ("eac3", 6)


def test_a_track_without_tags_says_nothing_instead_of_falling() -> None:
    """Безымянная дорожка - обычное дело, и паспорт обязан её пережить."""
    track = _track(0, {"codec_name": "aac"})

    assert track.language is None and track.title is None
    assert track.channels == 0
