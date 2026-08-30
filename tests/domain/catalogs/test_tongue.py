"""Зеркало языка показа: умолчание английское, назначает его корень."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from torrcast.domain.catalogs.tongue import EN, RU, _choose_tongue, tongue
from torrcast.domain.torrcast_error import TorrcastError


@pytest.fixture(autouse=True)
def _restore() -> Iterator[None]:
    was = tongue()
    yield
    _choose_tongue(was)


def test_default_tongue_is_english() -> None:
    assert tongue() == EN


def test_chosen_tongue_is_remembered() -> None:
    _choose_tongue(RU)
    assert tongue() == RU
    _choose_tongue(EN)
    assert tongue() == EN


def test_a_typo_in_the_setting_is_not_silently_worn_as_english() -> None:
    """🔴 Просьба tc930: опечатка в настройке обязана быть отличима от честного `--en`.

    Раньше ``_choose_tongue("de")`` принимался молча и вырождался в английский через
    запасной каталог (:mod:`torrcast.domain.catalogs.phrase`) - неотличимо от
    настоящего выбора английского.
    """
    with pytest.raises(TorrcastError):
        _choose_tongue("de")
    assert tongue() == EN, "отказ не имеет права оставить язык подменённым наполовину"
