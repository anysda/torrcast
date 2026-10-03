"""Зеркало :mod:`torrcast.domain._release_marks`: метки в зоне пометок имени."""

import dataclasses
import re
from collections.abc import Iterator

import pytest

from torrcast.domain import _release_marks
from torrcast.domain._name_data.data_1 import _EXTRAS_RE
from torrcast.domain.release import Release


def test_a_mark_inside_the_title_itself_is_not_a_mark() -> None:
    """Метки судятся в зоне пометок: название картины из имени раздачи сначала вычёркивается."""
    release = Release(
        raw_name="Дополнительные материалы 2019 1080p", title="Дополнительные материалы"
    )

    assert release.untitled.strip() == "2019 1080p"
    assert release.extras is False


def test_a_film_with_extras_attached_stays_a_film() -> None:
    """«Фильм + допы» - это фильм: метка после плюса приложением раздачу не делает."""
    assert Release(raw_name="Кино 1080p + бонусы", title="Кино").extras is False


class _Counted:
    """The extras pattern that counts its scans of a name."""

    def __init__(self, real: re.Pattern[str]) -> None:
        self.real = real
        self.scans = 0

    def finditer(self, text: str) -> Iterator[re.Match[str]]:
        self.scans += 1
        return self.real.finditer(text)


def test_a_name_asked_again_is_not_scanned_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """Метки одного имени за поиск спрашивают десятки раз и у копий: проход один на текст."""
    counted = _Counted(_EXTRAS_RE)
    monkeypatch.setattr(_release_marks, "_EXTRAS_RE", counted)
    release = Release(raw_name="Тачки 2006 BDRip фильм о фильме 0.4 GB", title="Тачки")

    marks = [dataclasses.replace(release, size=number).extras_mark for number in range(50)]

    assert marks == ["фильм о фильме"] * 50
    assert counted.scans == 1
