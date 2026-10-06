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


def test_a_native_show_keeps_its_own_track_when_the_file_changes() -> None:
    """Картина своего языка: в новом файле играет её дорожка, а не дубляж поверх неё,
    хотя дорожек две и ни одна не безымянная одиночка."""
    entry = Entry(title="Сериал", magnet="m", native=True)
    next_file = Media(60.0, tracks=(AudioTrack(0, "rus", "Дубляж"), AudioTrack(1, "rus")))

    selected = reselect_voice(entry, next_file)

    assert selected.audio == 1


def test_a_bare_pack_track_is_found_by_the_release_studios_kept_in_the_record() -> None:
    """Дорожки пака подписаны голым ``rus``: чья вторая, говорит только имя раздачи,
    и запомненная озвучка находится по студиям из записи, а не уходит в умолчание."""
    entry = Entry(
        title="Сериал",
        magnet="m",
        voice="Good People",
        studios=["The Kitchen Russia", "Good People"],
    )
    next_file = Media(60.0, tracks=(AudioTrack(0, "rus"), AudioTrack(1, "rus")))

    selected = reselect_voice(entry, next_file)

    assert selected.audio == 1
