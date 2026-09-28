"""Сторож единственного языка веба."""

from __future__ import annotations

from pathlib import Path


def test_the_web_catalog_cannot_gain_a_russian_peer() -> None:
    root = Path(__file__).parents[4] / "torrcast" / "domain" / "catalogs" / "web"
    assert not (root / "ru.py").exists()
