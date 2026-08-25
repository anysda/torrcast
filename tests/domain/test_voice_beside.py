"""Проверяет правило «звук отдельным файлом рядом с видео»."""

from torrcast.domain.torr_file import TorrFile
from torrcast.domain.voice_beside import voice_beside


def _files(*names: str) -> list[TorrFile]:
    return [TorrFile(index=i, name=name, size=1000) for i, name in enumerate(names)]


def test_same_name_wins_across_folders() -> None:
    """Студия кладёт дорожку в свою папку, а связывает её с серией имя, а не место."""
    files = _files("Erin/Erin - 01.mkv", "Erin/Sound/Erin - 01.mka", "Erin/Sound/Erin - 02.mka")
    found = voice_beside(files[0], files)
    assert found is not None and found.name.endswith("Sound/Erin - 01.mka")


def test_each_episode_takes_its_own_track() -> None:
    """У каждой серии своя дорожка: правило имени держит весь сезон, а не первую серию."""
    files = _files("Erin - 01.mkv", "Erin - 02.mkv", "Sound/Erin - 01.mka", "Sound/Erin - 02.mka")
    found = voice_beside(files[1], files)
    assert found is not None and found.name == "Sound/Erin - 02.mka"


def test_single_track_beside_single_video_is_taken() -> None:
    """Фильм плюс одна дорожка: спутать не с чем, имя совпадать не обязано."""
    files = _files("Movie.2019.1080p.mkv", "rus.mka")
    found = voice_beside(files[0], files)
    assert found is not None and found.name == "rus.mka"


def test_two_unmatched_tracks_answer_nothing() -> None:
    """Дорожек несколько, имя ни одну не называет - молчим: рядом с русской лежит чужая."""
    files = _files("Movie.mkv", "eng.mka", "rus.mka")
    assert voice_beside(files[0], files) is None


def test_single_track_beside_many_videos_answers_nothing() -> None:
    """Одна дорожка на пятьдесят серий - это не «дорожка этой серии»."""
    files = _files("e01.mkv", "e02.mkv", "e03.mkv", "sound.mka")
    assert voice_beside(files[0], files) is None


def test_release_without_sound_files_answers_nothing() -> None:
    """Субтитры и картинки звуком не считаются: их расширений в списке нет."""
    files = _files("Movie.mkv", "Movie.srt", "cover.jpg")
    assert voice_beside(files[0], files) is None
