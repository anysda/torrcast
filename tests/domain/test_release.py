"""Зеркало :mod:`torrcast.domain.release`."""

from torrcast.domain.release import Release


def test_release_is_exposed() -> None:
    assert Release is not None


def test_studios_come_from_the_marks_not_from_the_title() -> None:
    release = Release(
        raw_name="Гоблин / Goblin (2020) BDRip 1080p, Dub (The Kitchen Russia)",
        title="Гоблин",
        original="Goblin",
    )
    assert [studio.name for studio in release.studios] == ["The Kitchen Russia"]


def test_the_named_codec_is_spelled_the_way_the_profile_spells_it() -> None:
    """Имя пишет кодек по-человечески, профиль судит по ключу - перевод один на оба."""
    assert Release(raw_name="", title="", codec="HEVC").named_codec == "hevc"
    assert Release(raw_name="", title="", codec="H.264").named_codec == "h264"
    assert Release(raw_name="", title="", codec="MPEG-4").named_codec == "mpeg4"
    assert Release(raw_name="", title="", codec="AV1").named_codec == "av1"


def test_a_silent_name_hands_the_profile_no_codec_at_all() -> None:
    """Пусто - это «имя не сказало»: приговор выносит умолчание профиля, а не мы."""
    assert Release(raw_name="", title="", codec=None).named_codec == ""


def test_a_named_hdr_promises_ten_bits_of_colour() -> None:
    """Восьмибитного HDR не бывает: и HDR10, и Dolby Vision несут десять."""
    assert Release(raw_name="", title="", hdr=True).named_depth == 10
    assert Release(raw_name="", title="", hdr=False).named_depth == 0
