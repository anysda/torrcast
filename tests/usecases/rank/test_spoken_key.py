"""Зеркало :mod:`torrcast.usecases.rank.spoken_key`: ключ языка, а не само слово."""

from torrcast.domain.audio_track import AudioTrack
from torrcast.usecases.rank.spoken_key import ORIGINAL_KEY, spoken_key


def test_the_code_is_read_loosely_and_an_unlisted_one_is_the_original() -> None:
    keys = [
        spoken_key(AudioTrack(index=0, language=language))
        for language in (" ENG ", "ja", "ukr", "hun")
    ]

    assert keys == ["rank.lang_english", "rank.lang_japanese", "rank.lang_ukrainian", ORIGINAL_KEY]
