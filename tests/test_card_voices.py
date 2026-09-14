"""Строки выбора озвучки: все дорожки раздачи, подписанные языком страницы."""

from __future__ import annotations

import pytest

from tests.usecases.rank.releases import media, track
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.json_value import JsonValue
from web.card_voices import card_voices
from web.heard import Heard


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Дефолт дорожки берётся русской лестницей, как у ``cast voices`` на русском продукте."""


def _heard(*tracks: AudioTrack) -> Heard:
    return Heard(media(tracks=tracks), native=False, studios=())


def _field(rows: list[JsonValue], name: str) -> list[JsonValue]:
    return [row[name] for row in rows if isinstance(row, dict)]


def test_english_and_japanese_tracks_stand_beside_the_russian_one() -> None:
    """🔴 Дефект владельца 14-09-2026: нерусских дорожек в списке веба не было вовсе."""
    heard = _heard(track(0, "rus", "Dub"), track(1, "eng", "Original"), track(2, "jpn", None))

    rows = card_voices(heard, "ru")

    assert _field(rows, "label") == [
        "русский · Dub",
        "английский · Original",
        "японский",
    ]
    assert _field(rows, "default") == [True, False, False]


def test_the_english_page_names_the_same_tracks_in_english() -> None:
    heard = _heard(track(0, "rus", "Dub"), track(1, "eng", None), track(2, "ukr", None))

    rows = card_voices(heard, "en")

    assert _field(rows, "label") == ["Russian · Dub", "English", "Ukrainian"]


def test_the_russian_page_names_ukrainian_in_russian() -> None:
    assert _field(card_voices(_heard(track(0, "ukr", "Dub")), "ru"), "label") == [
        "украинский · Dub"
    ]


def test_the_voice_name_is_what_survives_another_release_the_show_may_take() -> None:
    """Имя уходит показу как ``--voice``, а показ отбирает раздачу заново: живой замер
    выбрал «eng · Eng», показ взял раздачу с «eng · Original» и отказал."""
    heard = _heard(
        track(0, "rus", "MVO (LostFilm)"),
        track(1, "eng", "Original"),
        track(2, "jpn", "Commentary"),
        track(3, "jpn", "Original"),
    )

    rows = card_voices(heard, "ru")

    assert _field(rows, "name") == ["LostFilm", "eng", "jpn · Commentary", "jpn · Original"]


def test_twin_tracks_that_no_word_tells_apart_are_named_by_number() -> None:
    """Живой замер: у раздачи две дорожки ``rus`` без заголовка, вторая была не выбираема."""
    heard = _heard(track(0, "rus", None), track(1, "rus", None), track(2, "jpn", None))

    rows = card_voices(heard, "ru")

    assert _field(rows, "name") == ["1", "2", "jpn"]
    assert _field(rows, "label") == ["русский", "русский", "японский"]


def test_an_unnamed_language_is_not_called_original_and_an_unknown_code_stays_a_code() -> None:
    heard = _heard(track(0, "und", "Дубляж"), track(1, "hun", "Original"), track(2, None, None))

    rows = card_voices(heard, "ru")

    assert _field(rows, "label") == [
        "Дубляж",
        "hun · Original",
        "дорожка 3",
    ]


def test_no_heard_release_gives_no_rows() -> None:
    assert card_voices(None, "ru") == []
