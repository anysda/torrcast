"""Запомненный выбор вслух: ключ памяти под ним не двигается ни на байт (TC-942)."""

from __future__ import annotations

from tests.usecases.rank.releases import media, track
from torrcast.domain.catalogs.tongue import EN, RU, _choose_tongue
from torrcast.usecases.rank.pick_voice import pick_voice
from torrcast.usecases.rank.spoken_voice import spoken_voice


def test_foreign_text_is_left_untouched(_english: None) -> None:
    # «Дубляж (MovieDalen)» - надпись самой раздачи, не наше слово.
    assert spoken_voice("rus · Дубляж (MovieDalen)") == "rus · Дубляж (MovieDalen)"


def test_the_fallback_speaks_the_product_language() -> None:
    _choose_tongue(EN)
    assert spoken_voice("дорожка 3") == "track 3"
    _choose_tongue(RU)
    assert spoken_voice("дорожка 3") == "дорожка 3"


class _Args:
    """Ровно то, что правило у разобранной строки и спрашивает."""

    def __init__(self, voice: int | str | None = None) -> None:
        self.voice = voice


def test_remembered_voice_survives_a_language_switch() -> None:
    """Запомненный выбор переживает смену языка продукта (TC-942, приёмка п.2): ключ
    памяти (:attr:`torrcast.domain.audio_track.AudioTrack.label`) не двигается, значит
    найдётся под любым языком."""
    tracks = (track(0, "rus", "Дубляж"), track(1, "eng", "Original"))
    _choose_tongue(RU)
    found_at, remembered = pick_voice(media(tracks=tracks), _Args(voice=1))
    assert remembered  # явный выбор - и только он - лёг в память

    _choose_tongue(EN)
    found, _ = pick_voice(media(tracks=tracks), _Args(), remembered=remembered)
    assert found == found_at

    _choose_tongue(RU)
    found, _ = pick_voice(media(tracks=tracks), _Args(), remembered=remembered)
    assert found == found_at


def test_a_fallback_labeled_voice_survives_a_language_switch() -> None:
    """Тот самый рискованный случай: подпись без языка и заголовка тоже уезжает в
    память и тоже обязана находиться под любым языком продукта."""
    blank = track(0, None, None)
    other = track(1, "eng", "Original")
    _choose_tongue(RU)
    found_at, remembered = pick_voice(media(tracks=(blank, other)), _Args(voice=1))
    assert remembered == "дорожка 1"

    _choose_tongue(EN)
    found, _ = pick_voice(media(tracks=(blank, other)), _Args(), remembered=remembered)
    assert found == found_at
    # Показанная человеку форма - на языке продукта, хранимая - нет.
    assert spoken_voice(remembered) == "track 1"

    _choose_tongue(RU)
    assert spoken_voice(remembered) == "дорожка 1"
