"""Зеркало пересчёта дорожки на следующем файле сериала."""

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.entry import Entry
from torrcast.domain.media import Media
from torrcast.usecases.rank.reselect_voice import reselect_voice


def test_a_voice_name_is_resolved_in_the_new_files_layout() -> None:
    entry = Entry(title="Сериал", magnet="m", audio=0, voice="rus")
    next_file = Media(60.0, tracks=(AudioTrack(0, "eng"), AudioTrack(1, "rus")))

    selected = reselect_voice(entry, next_file)

    assert selected.audio == 1
