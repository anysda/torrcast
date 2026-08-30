"""Вид перевода вслух; сравнение (:attr:`AudioTrack.kind`) под словом не двигается."""

from __future__ import annotations

from torrcast.usecases.rank.spoken_kind import spoken_kind


def test_every_step_of_the_ladder_speaks_english(_english: None) -> None:
    assert spoken_kind("дубляж") == "the dub"
    assert spoken_kind("многоголосый") == "the multi-voice one"
    assert spoken_kind("двухголосый") == "the dual-voice one"
    assert spoken_kind("одноголосый") == "the single-voice one"


def test_unknown_or_empty_kind_is_returned_as_is(_english: None) -> None:
    # Слово, которого лестница не знает (или пустое), возвращается как есть - не
    # придумываем перевод тому, чего не поняли.
    assert spoken_kind("") == ""
    assert spoken_kind("закадровый-неизвестный") == "закадровый-неизвестный"


def test_russian_form_is_exactly_the_comparison_word(_russian_product: None) -> None:
    """Русская форма - ровно то же слово, каким :attr:`AudioTrack.kind` называет себя
    в сравнении (:data:`torrcast.domain.audio_track._VOICE_STEPS`)."""
    for kind in ("дубляж", "многоголосый", "двухголосый", "одноголосый"):
        assert spoken_kind(kind) == kind
