"""Зеркало :mod:`torrcast.domain.release`: что раздача говорит о себе отбору."""

from torrcast.domain.episode import Episode
from torrcast.domain.release import Release


def _named(raw_name: str, **fields: object) -> Release:
    return Release(raw_name=raw_name, title="Кино", **fields)  # type: ignore[arg-type]


def test_the_codec_of_the_name_is_told_in_the_words_of_the_receiver() -> None:
    """Приёмник судит кодек одним ключом, а имя раздачи пишет его по-человечески."""
    assert _named("Кино HEVC", codec="HEVC").named_codec == "hevc"
    assert _named("Кино").named_codec == ""


def test_the_hdr_mark_promises_ten_bits_of_colour() -> None:
    """Восьмибитного HDR не бывает, и осторожному приёмнику этого уже достаточно."""
    assert _named("Кино HDR", hdr=True).named_depth == 10
    assert _named("Кино").named_depth == 0


def test_the_height_of_the_frame_is_read_out_of_the_quality() -> None:
    assert _named("Кино", quality="1080p").height == 1080
    assert _named("Кино", quality="576i").interlaced
    assert _named("Кино").height == 0


def test_a_season_release_covers_every_episode_of_its_season() -> None:
    """Сезонная раздача серий не перечисляет, но нужную серию она содержит."""
    season = _named("Сериал", season=2)

    assert season.covers(2)
    assert not season.covers(3)
    assert season.covers_episode(Episode(season=2, episode=7))


def test_a_release_that_names_its_episodes_covers_only_them() -> None:
    part = _named("Сериал", season=1, episodes=(1, 2, 3))

    assert part.covers_episode(Episode(season=1, episode=2))
    assert not part.covers_episode(Episode(season=1, episode=9))


def test_a_release_that_names_nothing_covers_whatever_is_asked() -> None:
    """Молчание раздачи о сезоне - это не отказ: такие раздают сериал целиком."""
    whole = _named("Сериал")

    assert whole.covers(5)
    assert whole.covers_episode(Episode(season=5, episode=5))


def test_a_dated_release_is_recognised_by_its_source_and_codec() -> None:
    """Старьё берётся только когда другого нет, и узнаётся оно по имени."""
    assert _named("Кино DivX", codec="MPEG-4").dated
    assert _named("Кино.avi").dated
    assert not _named("Кино BDRip", codec="H.264", source="BDRip").dated
