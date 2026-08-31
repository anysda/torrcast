"""Английский каталог кластера ``stream_probe``: он же умолчание, он же запасной."""

from __future__ import annotations

import re

from torrcast.domain.catalogs.stream_probe.en import en as english

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def test_english_catalog_holds_no_russian() -> None:
    russian = [key for key, line in english().items() if _CYRILLIC.search(line)]
    assert russian == []


def test_every_key_names_its_cluster() -> None:
    stray = [key for key in english() if not key.startswith("stream_probe.")]
    assert stray == []
    assert english()["stream_probe.service_down"] == "TorrServer does not answer"
