"""Зеркало :mod:`torrcast.domain.normalize_quality`: качество, названное одним словом."""

from torrcast.domain.normalize_quality import _normalize_quality


def test_the_marketing_names_of_the_tallest_frame_become_its_height() -> None:
    """Профиль приёмника судит по высоте кадра, а имя раздачи пишет «4K» и «UHD»."""
    assert _normalize_quality("4K") == "2160p"
    assert _normalize_quality("UHD") == "2160p"


def test_a_height_stays_a_height_and_loses_only_its_case() -> None:
    assert _normalize_quality("1080P") == "1080p"
