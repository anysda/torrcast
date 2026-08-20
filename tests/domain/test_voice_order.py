"""Проверки порядка озвучек."""

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.voice_order import voice_order


def test_russian_dub_precedes_original() -> None:
    assert voice_order(AudioTrack(1, "rus", "Дубляж")) < voice_order(
        AudioTrack(0, "eng", "Original")
    )


def test_a_native_picture_plays_its_own_track_and_not_a_dub_over_it() -> None:
    """Русский фильм: подписанный дубляж - переозвучка, а безымянная дорожка - сам фильм."""
    own, dub = AudioTrack(1, "rus"), AudioTrack(0, "rus", "[DUB] DVD-R5 AMALGAMA")

    assert voice_order(own, native=True) < voice_order(dub, native=True)
    assert voice_order(dub) < voice_order(own)


def test_a_silent_origin_leaves_the_ladder_exactly_as_it_was() -> None:
    """Паспорт происхождения молчит - лестница прежняя, дубляж по-прежнему лучший."""
    own, dub = AudioTrack(1, "rus"), AudioTrack(0, "rus", "Дубляж")

    assert voice_order(dub, native=False) < voice_order(own, native=False)


def test_a_native_picture_still_puts_russian_above_any_foreign_track() -> None:
    """«Есть ли русский вообще» важнее конкретной дорожки: чужой звук не поднимается."""
    dub = AudioTrack(1, "rus", "Дубляж")

    assert voice_order(dub, native=True) < voice_order(AudioTrack(0, "eng", "Original"), True)
    assert voice_order(dub, native=True) < voice_order(AudioTrack(0, "jpn"), True)


def test_a_service_track_of_a_native_picture_stays_at_the_very_bottom() -> None:
    """Тифлокомментарий русский и безымянный по виду перевода - но слушать хотели фильм."""
    blind = AudioTrack(0, "rus", "Дубляж для слабовидящих")

    assert voice_order(AudioTrack(1, "rus"), native=True) < voice_order(blind, native=True)


def test_a_known_studio_of_a_native_picture_is_a_re_voicing_and_not_the_original() -> None:
    """Знакомая студия - переводчик: у отечественной картины её дорожка тоже переозвучка."""
    own, studio = AudioTrack(1, "rus"), AudioTrack(0, "rus", "LostFilm")

    assert voice_order(own, native=True) < voice_order(studio, native=True)


def test_an_unknown_title_does_not_bring_the_choice_down() -> None:
    """Незнакомая подпись оставляет дорожку своей: у русской картины она и есть фильм."""
    own = AudioTrack(1, "rus", "AC3 5.1 448 Kbps")

    assert voice_order(own, native=True) < voice_order(AudioTrack(0, "rus", "Дубляж"), True)
