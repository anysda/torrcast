"""Ворота отбора: годится ли раздача в дефолт Enter."""

from __future__ import annotations

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.usecases.rank.is_candidate import is_candidate


def test_a_prime_release_within_the_ceiling_is_a_candidate() -> None:
    assert is_candidate(rel(), RUNTIME, 20.0)


def test_a_disc_an_extra_and_a_fat_one_never_pass() -> None:
    assert not is_candidate(rel(name="Кино (1999) BDMV"), RUNTIME, 20.0)
    assert not is_candidate(rel(name="Кино: трейлер", size_gb=0.4), RUNTIME, 20.0)
    assert not is_candidate(rel(size_gb=28), RUNTIME, 20.0)


def test_a_silent_name_passes_only_through_open_gates() -> None:
    """Судить её будет ffprobe после выбора: механизм отбраковки уже стоит на пути."""
    quiet = rel(name="Кино (1999)", quality=None, codec=None, source=None)
    assert not is_candidate(quiet, RUNTIME, 20.0)
    assert is_candidate(quiet, RUNTIME, 20.0, loose=True)


def test_open_gates_never_let_a_non_video_in() -> None:
    """Репак игры о качестве молчит по той причине, что видео там нет вовсе."""
    game = rel(
        name="One Piece: Pirate Warriors 4 ... PC | RePack",
        title="One Piece",
        quality=None,
        codec=None,
        source=None,
        kind="other",
    )
    assert not is_candidate(game, RUNTIME, 20.0, loose=True)


def test_open_gates_do_not_forgive_a_name_that_told_the_truth() -> None:
    """Названный HEVC остаётся снаружи: про него известно, а не неизвестно."""
    assert not is_candidate(rel(codec="HEVC"), RUNTIME, 20.0, loose=True)


def test_hevc_passes_by_the_last_hope_or_by_the_receivers_word() -> None:
    hevc = rel(codec="HEVC")
    assert is_candidate(hevc, RUNTIME, 20.0, last=True)
    assert is_candidate(hevc, RUNTIME, 20.0, copy_hevc=True)
    assert not is_candidate(rel(codec="HEVC", size_gb=28), RUNTIME, 20.0, copy_hevc=True), (
        "профиль не снимает потолок битрейта"
    )


def test_the_denominator_decides_whether_an_honest_1080p_is_a_candidate() -> None:
    """🔴 TC-185. Потолок тот же, длительность разная - и годность у файла разная.

    Это и был молчаливый отсев: прикидка «фильм это два часа» выкидывала честный
    16.5-гигабайтный 1080p «Интерстеллара», который в свои 2 ч 49 мин в потолок влезает.
    """
    full = rel(name="Интерстеллар / Interstellar (2014) BDRip 1080p", size_gb=16.5, seeders=90)

    assert not is_candidate(full, RUNTIME, 16.0), "прикидка выкидывает честный 1080p"
    assert is_candidate(full, 169 * 60.0, 16.0), "настоящая длительность его возвращает"
