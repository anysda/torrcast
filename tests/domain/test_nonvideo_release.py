"""Зеркало :mod:`torrcast.domain.nonvideo_release`: не-видео раздача по имени (N1-N4)."""

import re

import pytest

import torrcast.domain.nonvideo_release as nonvideo_release
from torrcast.domain.nonvideo_release import _is_nonvideo_release


def test_n1_audio_without_video_mark_is_nonvideo() -> None:
    assert _is_nonvideo_release(
        "Семнадцать мгновений весны / Михаил Таривердиев OST (1973) APE by гаврила"
    )


def test_n2_art_pack_is_nonvideo() -> None:
    assert _is_nonvideo_release("Chainsaw Man / Человек-бензопила [Art] [2021] [JPG]")
    assert _is_nonvideo_release("Naruto / Наруто [Art] [2020] [JPG]")


def test_unnamed_english_volume_packs_are_nonvideo() -> None:
    assert _is_nonvideo_release(
        "Life with an Ordinary Guy Who Reincarnated into a Total Fantasy Knockout v01-10"
    )
    assert _is_nonvideo_release("I Was Sacrificed to a Vampire, But He Spoils Me Instead! 001-011")
    assert _is_nonvideo_release(
        "Dragon and Flower - The Timid Princess and the Ice Sword's Loyalty 001-010"
    )
    assert _is_nonvideo_release("The Apothecary Diaries v01-13")
    assert _is_nonvideo_release("Frieren: Beyond Journey's End 001-140")
    assert _is_nonvideo_release("A Sign of Affection Vol. 01-11")


def test_an_unmarked_two_digit_episode_range_stays_video() -> None:
    assert not _is_nonvideo_release("A Series (2019) [01-03 из 03 + Фильм о фильме]")


def test_removing_the_volume_range_would_let_packs_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отрицательная проба: без диапазона томов пак снова выглядит картиной."""
    monkeypatch.setattr(
        nonvideo_release,
        "_TEXT_RE",
        re.compile(
            r"(?i)(?<![a-z])(pdf|epub|fb2|djvu|cbr|cbz|mobi)(?![a-z])"
            r"|манга|манхва|комикс|light novel|ラノベ|\bsheet music\b|\bguitar tablature\b"
        ),
    )
    names = [
        "The Apothecary Diaries v01-13",
        "Frieren: Beyond Journey's End 001-140",
        "A Sign of Affection Vol. 01-11",
    ]
    assert not any(nonvideo_release._is_nonvideo_release(name) for name in names)


def test_n4_game_is_nonvideo() -> None:
    assert _is_nonvideo_release(
        "Ведьмак 3: Дикая Охота ... [v 1.31 + DLCs, Mod] (2015) PC | Repack-xatab"
    )


def test_ordinary_release_is_not_flagged() -> None:
    assert not _is_nonvideo_release("Брат 1997 BDRip")
