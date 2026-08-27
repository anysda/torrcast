"""Имя заголовка места: приставка, слот и расширение."""

from __future__ import annotations

from torrcast.domain.head_name import head_name


def test_the_head_of_a_place_is_named_by_its_slot() -> None:
    """Заголовок зовут по месту, которому он принадлежит."""
    assert head_name(7) == "head7.mp4"


def test_the_suffix_is_an_argument_because_the_head_has_two_names() -> None:
    """Расширение доводом: сам заголовок и кусок с приставленным заголовком - разное."""
    assert head_name(7, ".m4s") == "head7.m4s"


def test_the_head_never_looks_like_a_segment_to_the_run_directory_glob() -> None:
    """Каталоги перебираются глобом ``v*``, и заголовок обязан в него не попасть."""
    assert not head_name(3).startswith("v")
    assert not head_name(3, ".ts").startswith("v")
