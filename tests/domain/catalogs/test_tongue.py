"""Зеркало языка показа: умолчание английское, назначает его корень."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from torrcast.domain.catalogs.tongue import _choose_tongue, tongue


@pytest.fixture(autouse=True)
def _restore() -> Iterator[None]:
    was = tongue()
    yield
    _choose_tongue(was)


def test_default_tongue_is_english() -> None:
    assert tongue() == "en"


def test_chosen_tongue_is_remembered() -> None:
    _choose_tongue("ru")
    assert tongue() == "ru"
    _choose_tongue("en")
    assert tongue() == "en"
