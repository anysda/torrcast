"""Зеркало :mod:`torrcast.domain.media`: что паспорт говорит о ЗВУКЕ."""

import pytest

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет всего модуля - РУССКАЯ лестница озвучек, писанная до языкового яруса
    (:func:`torrcast.domain.voice_order._tier`). Умолчание продукта английское, и на нём
    набор остался бы зелёным, но мерил бы уже другой порядок: та же зелень отвечала бы
    на другой вопрос. Поэтому язык назван, а не унаследован."""


def test_an_unnamed_track_keeps_the_passport_from_calling_the_file_foreign() -> None:
    """Дорожка без тега языка - это незнание, а не «русской нет»: бракуем не по догадке."""
    media = Media(tracks=(AudioTrack(index=0, language=None),))

    assert (media.foreign, media.russian) == (False, False)


def test_a_native_picture_defaults_to_its_own_track_and_not_to_the_dub_over_it() -> None:
    """Живая приёмка: у русского фильма отбор брал «[DUB] DVD-R5 AMALGAMA» вместо оригинала."""
    tracks = (
        AudioTrack(index=0, language="rus", title="[DUB] DVD-R5 AMALGAMA"),
        AudioTrack(index=1, language="rus"),
        AudioTrack(index=2, language="eng"),
    )
    media = Media(tracks=tracks)

    assert (media.default_track(native=True), media.default_track()) == (1, 0)
