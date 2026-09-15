"""Зеркало :mod:`torrcast.domain.voice_folder`: язык файла звука по его каталогу."""

from __future__ import annotations

import pytest

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.voice_folder import voice_folder

_ROOT = "[SOFCJ-Raws] Naruto (DVDRip 768x576 HEVC VFR 10bit FLAC)"
_NAMELESS = Media(0.0, (AudioTrack(index=0, codec="ac3"),))


@pytest.mark.parametrize(
    ("path", "language"),
    [
        (f"{_ROOT}/Sound/Rus [Dub+MVO]/[2x2] [001-220] [MVO]/Naruto - 111.mka", "rus"),
        (f"{_ROOT}/Sound/Eng [Dub]/Naruto - 111 DVDRip.mka", "eng"),
        (f"{_ROOT}/RUS Sound/Naruto - 111.mka", "rus"),
        (f"{_ROOT}/Озвучка/Русская/Naruto - 111.mka", "rus"),
    ],
)
def test_a_folder_names_the_language_of_a_nameless_sound_file(path: str, language: str) -> None:
    assert [t.language for t in voice_folder(_NAMELESS, path).tracks] == [language]


@pytest.mark.parametrize(
    "path",
    [
        "Russian Doll S01/Sound/Russian Doll - 01.mka",
        f"{_ROOT}/Sound/Naruto - 111.mka",
        f"{_ROOT}/Sound/Rustam/Naruto - 111.mka",
        "Naruto - 111.mka",
    ],
)
def test_the_release_root_or_a_mute_folder_names_nothing(path: str) -> None:
    assert voice_folder(_NAMELESS, path) is _NAMELESS


def test_a_language_the_file_named_itself_is_not_overridden() -> None:
    told = Media(0.0, (AudioTrack(index=0, language="jpn"),))
    assert voice_folder(told, f"{_ROOT}/Sound/Rus/Naruto - 111.mka") is told
