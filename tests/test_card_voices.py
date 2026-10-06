"""Строки выбора озвучки: все дорожки раздачи подписаны по-английски."""

from __future__ import annotations

import pytest

from tests.usecases.rank.releases import media, track
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from web.card_voices import card_voices
from web.heard import Heard


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Выбор дорожки сохраняет язык продукта, хотя подпись страницы английская."""


def _heard(*tracks: AudioTrack) -> Heard:
    return Heard(media(tracks=tracks), native=False, studios=())


def _field(rows: list[JsonValue], name: str) -> list[JsonValue]:
    return [row[name] for row in rows if isinstance(row, dict)]


def test_english_and_japanese_tracks_stand_beside_the_russian_one() -> None:
    """🔴 Дефект владельца 14-09-2026: нерусских дорожек в списке веба не было вовсе."""
    heard = _heard(track(0, "rus", "Dub"), track(1, "eng", "Original"), track(2, "jpn", None))

    rows = card_voices(heard)

    assert _field(rows, "label") == [
        "Russian · Dub",
        "English · Original",
        "Japanese",
    ]
    assert _field(rows, "default") == [True, False, False]


def test_the_voice_name_is_what_survives_another_release_the_show_may_take() -> None:
    """Имя уходит показу как ``--voice``, а показ отбирает раздачу заново: живой замер
    выбрал «eng · Eng», показ взял раздачу с «eng · Original» и отказал."""
    heard = _heard(
        track(0, "rus", "MVO (LostFilm)"),
        track(1, "eng", "Original"),
        track(2, "jpn", "Commentary"),
        track(3, "jpn", "Original"),
    )

    rows = card_voices(heard)

    assert _field(rows, "name") == ["LostFilm", "eng", "jpn · Commentary", "jpn · Original"]


def test_twin_tracks_that_no_word_tells_apart_are_named_by_number() -> None:
    """Живой замер: у раздачи две дорожки ``rus`` без заголовка, вторая была не выбираема."""
    heard = _heard(track(0, "rus", None), track(1, "rus", None), track(2, "jpn", None))

    rows = card_voices(heard)

    assert _field(rows, "name") == ["1", "2", "jpn"]
    assert _field(rows, "label") == ["Russian", "Russian", "Japanese"]


def test_an_unnamed_language_is_not_called_original_and_an_unknown_code_stays_a_code() -> None:
    heard = _heard(track(0, "und", "Дубляж"), track(1, "hun", "Original"), track(2, None, None))

    rows = card_voices(heard)

    assert _field(rows, "label") == [
        "Дубляж",
        "hun · Original",
        "track 3",
    ]


def test_no_heard_release_gives_no_rows() -> None:
    assert card_voices(None) == []


def test_a_lone_unnamed_track_of_a_foreign_picture_says_language_not_stated() -> None:
    """🔴 TC-1288. Иностранная картина, одна дорожка без тега - «язык не назван», не номер."""
    heard = Heard(media(tracks=(track(0, None, None),)), native=False, studios=())

    rows = card_voices(heard)

    assert _field(rows, "label") == ["language not stated"]


def test_a_lone_unnamed_track_of_a_native_picture_says_russian() -> None:
    """🔴 TC-1288. Отечественный сериал, дорожка без тега - «Русский», не номер."""
    heard = Heard(media(tracks=(track(0, None, None),)), native=True, studios=())

    rows = card_voices(heard)

    assert _field(rows, "label") == ["Russian"]


def test_two_unnamed_native_tracks_stay_numbered() -> None:
    """Происхождение говорит язык картины, но не различает две дорожки между собой."""
    heard = Heard(
        media(tracks=(track(0, None, None), track(1, None, None))),
        native=True,
        studios=(),
    )

    assert _field(card_voices(heard), "label") == ["track 1", "track 2"]


_HASH = "a" * 40


def _bookmark(audio: int, magnet_hash: str = _HASH) -> Entry:
    """Начатый фильм на русской озвучке: его продолжит «Играть» своей записью."""
    magnet = "magnet:?xt=urn:btih:" + magnet_hash
    return Entry(title="Интерстеллар", magnet=magnet, dur=10143.9, pos=86.4, audio=audio)


def _interstellar() -> Heard:
    tracks = (track(0, "rus", "DUB"), track(1, "rus", "MVO"), track(2, "eng", "Original"))
    return Heard(media(tracks=tracks), native=False, studios=(), release=_HASH)


def test_the_bookmark_track_is_marked_not_the_default_one() -> None:
    """Живой дефект: закладка на русской озвучке, а подсвечен английский оригинал."""
    heard = _interstellar()
    english = heard.default

    rows = card_voices(heard, _bookmark(audio=1))

    assert english != 1
    assert _field(rows, "default") == [False, True, False]


def test_a_bookmark_of_another_release_does_not_move_the_mark() -> None:
    """Номер дорожки чужой раздачи к этой не относится: отметка остаётся на умолчании."""
    heard = _interstellar()
    expected = [index == heard.default for index in range(3)]

    rows = card_voices(heard, _bookmark(audio=1, magnet_hash="b" * 40))

    assert _field(rows, "default") == expected


def test_a_bookmark_track_out_of_range_falls_back_to_the_default() -> None:
    """Запись с номером, которого в паспорте нет, отметку не теряет."""
    heard = _interstellar()
    expected = [index == heard.default for index in range(3)]

    rows = card_voices(heard, _bookmark(audio=7))

    assert _field(rows, "default") == expected
