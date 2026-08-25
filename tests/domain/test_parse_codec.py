"""Зеркало :mod:`torrcast.domain.parse_codec`: кодек, названный именем раздачи."""

from torrcast.domain.parse_codec import _parse_codec


def test_every_kind_of_writing_leads_to_one_name_of_the_codec() -> None:
    """Приёмник судит кодеки по одному ключу, и имена раздач сводятся к нему тут."""
    assert _parse_codec("Кино x265 1080p") == "HEVC"
    assert _parse_codec("Кино H.264") == "H.264"
    assert _parse_codec("Кино DivX") == "MPEG-4"
    assert _parse_codec("Кино AV1") == "AV1"


def test_the_newer_codec_wins_when_the_name_mentions_two() -> None:
    """Имя часто перечисляет оба; играть будет тот, которым сжато, - названный первым."""
    assert _parse_codec("Кино HEVC x264") == "HEVC"


def test_a_name_that_says_nothing_about_the_codec_leaves_it_unnamed() -> None:
    """Пусто - это «имя молчит», и приговор такому выносит умолчание профиля."""
    assert _parse_codec("Кино 1997 BDRip") is None
