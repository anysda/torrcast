"""Зеркало мерки расширения предмета: считать прибавку можно, пока есть от чего считать."""

from __future__ import annotations

from torrcast.usecases.discover._widened_subject import _widened_subject


def test_one_extra_picture_is_the_unglued_second_half() -> None:
    """Латинская половина не склеилась с русской - это та же картина, а не соседняя."""
    assert _widened_subject(3, 2) is False


def test_two_extra_pictures_widened_the_subject() -> None:
    """Оригинал притащил соседние картины вместо той же самой - выдачу не берём."""
    assert _widened_subject(4, 2) is True


def test_the_same_count_widened_nothing() -> None:
    """Картин столько же, сколько было - предмет поиска остался прежним."""
    assert _widened_subject(2, 2) is False


def test_an_empty_first_reel_has_no_subject_to_widen() -> None:
    """🔴 TC-866. Первый круг привёз ноль картин - расширять нечего, и мерка молчит.

    Живой стенд, «эксперементы лейн»: 0 картин по-русски, 24 после добора по
    ``Serial Experiments Lain``. Прежняя мерка читала это как расширение предмета и
    выбрасывала всю выдачу, оставляя человека с «ничего не нашлось» при живой картине.
    """
    assert _widened_subject(24, 0) is False


def test_an_empty_first_reel_takes_a_single_picture_too() -> None:
    """Та же ветка при одной приехавшей картине: отвергать её тем более не за что."""
    assert _widened_subject(1, 0) is False
