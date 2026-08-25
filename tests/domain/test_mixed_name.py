"""Имя склейки: приставка своя, а расширение - того контейнера, каким режет показ."""

from __future__ import annotations

from torrcast.domain.hls_settings import MIXED_PREFIX
from torrcast.domain.mixed_name import mixed_name
from torrcast.domain.segment_container import FMP4, MPEGTS


def test_the_suffix_of_a_merge_is_the_suffix_of_the_container() -> None:
    """Расширение выбирает муксер: под чужим склейка собирается не тем и не выходит."""
    assert mixed_name(7, MPEGTS) == f"{MIXED_PREFIX}7.ts"
    assert mixed_name(7, FMP4) == f"{MIXED_PREFIX}7.m4s"


def test_a_merge_is_not_mistaken_for_a_piece_of_the_grid() -> None:
    """Каталог прогона перебирается маской куска, и склейка обязана мимо неё пройти."""
    assert not mixed_name(0, FMP4).startswith("v")
    assert not mixed_name(0, MPEGTS).startswith("v")
