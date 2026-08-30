"""Проверки модели звуковой дорожки."""

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.catalogs.tongue import RU, _choose_tongue


def test_label_omits_unknown_language() -> None:
    assert AudioTrack(0, "und", "Дубляж / AC3 / 6 ch").label == "Дубляж"


def test_label_does_not_depend_on_product_language(_english: None) -> None:
    """label - ключ памяти (:attr:`torrcast.domain.entry.Entry.voice`): под любым языком
    продукта он обязан звучать побайтово одинаково, иначе старый запомненный выбор
    просто перестанет находиться (:meth:`torrcast.domain.media.Media.find_voice`)."""
    tracks = (
        AudioTrack(0, "und", "Дубляж / AC3 / 6 ch"),
        AudioTrack(1, "rus", "MVO (LostFilm)"),
        AudioTrack(2, None, None),  # запасная подпись - самый рискованный случай
        AudioTrack(3, "eng", "Original"),
    )
    under_english = [track.label for track in tracks]
    _choose_tongue(RU)
    under_russian = [track.label for track in tracks]
    assert under_english == under_russian
