"""Английский каталог кластера ``media_binaries``: он же умолчание, он же запасной."""

from __future__ import annotations

import re

from torrcast.domain.catalogs.media_binaries.en import en as english

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def test_english_catalog_holds_no_russian() -> None:
    russian = [key for key, line in english().items() if _CYRILLIC.search(line)]
    assert russian == []


def test_every_key_names_its_cluster() -> None:
    stray = [key for key in english() if not key.startswith("media_binaries.")]
    assert stray == []
    assert english()["media_binaries.ffmpeg_missing"] == "ffmpeg is not installed"
