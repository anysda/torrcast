"""Английский каталог кластера портовых слотов: он же умолчание, он же запасной."""

from __future__ import annotations

import re

from torrcast.domain.catalogs.ports.en import en as english

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def test_english_catalog_holds_no_russian() -> None:
    russian = [key for key, line in english().items() if _CYRILLIC.search(line)]
    assert russian == []


def test_every_key_names_its_cluster() -> None:
    stray = [key for key in english() if not key.startswith("ports.")]
    assert stray == []
    assert (
        english()["ports.show_unit_not_installed"]
        == "no show unit assigned: the app is not assembled"
    )
