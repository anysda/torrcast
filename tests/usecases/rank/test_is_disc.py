"""Образ диска: цельного файла внутри нет, и стримить там нечего."""

from __future__ import annotations

from tests.usecases.rank.releases import rel
from torrcast.usecases.rank.is_disc import is_disc


def test_a_disc_image_is_recognised_by_its_name() -> None:
    assert is_disc(rel(name="Кино (1999) BDMV 1080p"))
    assert is_disc(rel(name="Кино (1999) DVD9"))
    assert is_disc(rel(name="Кино (1999) BDRip 1080p ISO"))
    assert is_disc(rel(name="Кино (1999) DVD-Video"))


def test_an_ordinary_rip_is_not_a_disc() -> None:
    assert not is_disc(rel())
    assert not is_disc(rel(name="Кино (1999) WEB-DL 1080p"))
