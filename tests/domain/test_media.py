"""Зеркало :mod:`torrcast.domain.media`: что паспорт говорит о ЗВУКЕ."""

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media


def test_an_unnamed_track_keeps_the_passport_from_calling_the_file_foreign() -> None:
    """Дорожка без тега языка - это незнание, а не «русской нет»: бракуем не по догадке."""
    media = Media(tracks=(AudioTrack(index=0, language=None),))

    assert (media.foreign, media.russian) == (False, False)
