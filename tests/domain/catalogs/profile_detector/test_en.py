"""Английский каталог кластера выбора профиля: он же умолчание, он же запасной."""

from __future__ import annotations

import re

from torrcast.domain.catalogs.profile_detector.en import en as english

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def test_english_catalog_holds_no_russian() -> None:
    russian = [key for key, line in english().items() if _CYRILLIC.search(line)]
    assert russian == []


def test_every_key_names_its_cluster() -> None:
    stray = [key for key in english() if not key.startswith("profile_detector.")]
    assert stray == []
    assert english()["profile_detector.by_passport_prefix"] == "by passport:"
    assert (
        english()["profile_detector.named_manually"]
        == "manually named: receiver_profile={profile_key}"
    )
