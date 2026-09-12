"""Сторож режима ввода навигации на пустом месте страницы."""

from __future__ import annotations

from pathlib import Path

NAV = Path(__file__).resolve().parents[1] / "web" / "static" / "nav.js"


def test_pointer_away_keeps_the_keyboard_light_for_scrolling() -> None:
    """Колесо вне полки не должно сначала превратить клавиатурный режим в мышиный."""
    source = NAV.read_text(encoding="utf-8")

    assert "if (!under && TCNav.input === 'key') return;" in source
