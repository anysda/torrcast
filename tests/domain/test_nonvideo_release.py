"""Зеркало :mod:`torrcast.domain.nonvideo_release`: не-видео раздача по имени (N1-N4)."""

from torrcast.domain.nonvideo_release import _is_nonvideo_release


def test_n1_audio_without_video_mark_is_nonvideo() -> None:
    assert _is_nonvideo_release(
        "Семнадцать мгновений весны / Михаил Таривердиев OST (1973) APE by гаврила"
    )


def test_n2_art_pack_is_nonvideo() -> None:
    assert _is_nonvideo_release("Chainsaw Man / Человек-бензопила [Art] [2021] [JPG]")
    assert _is_nonvideo_release("Naruto / Наруто [Art] [2020] [JPG]")


def test_n4_game_is_nonvideo() -> None:
    assert _is_nonvideo_release(
        "Ведьмак 3: Дикая Охота ... [v 1.31 + DLCs, Mod] (2015) PC | Repack-xatab"
    )


def test_ordinary_release_is_not_flagged() -> None:
    assert not _is_nonvideo_release("Брат 1997 BDRip")
