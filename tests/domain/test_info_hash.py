"""Имя раздачи: тот же инфохэш, но спрошенный у самой раздачи, а не у голого магнита."""

from __future__ import annotations

from torrcast.domain.info_hash import info_hash
from torrcast.domain.release import Release

HEX = "4f2c1a90bd9e3f1fbaa1a8b8b7c0d1e2f3a4b5c6"


def _release(magnet: str) -> Release:
    return Release(raw_name="Тачки.2006.1080p", title="Тачки", magnet=magnet)


def test_a_release_is_named_by_the_hash_of_its_magnet() -> None:
    """Имя раздачи берётся у её магнита - разбор один на оба вопроса."""
    assert info_hash(_release(f"magnet:?xt=urn:btih:{HEX.upper()}&dn=Тачки")) == HEX


def test_a_release_without_a_hash_has_no_name() -> None:
    """Пустое имя - не имя: по нему показ ищет заново, а не берёт наугад."""
    assert info_hash(_release("magnet:?xt=urn:ed2k:abc")) == ""
    assert info_hash(_release("")) == ""
