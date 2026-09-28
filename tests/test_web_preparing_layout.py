"""Контракт ширины полосы подготовки.

Заголовок и полоса - соседи в ``player-screens.js``.  Grid-колонка берёт более
широкий из заголовка и прежних 35rem, поэтому полоса с ``width: 100%`` не может
закончиться раньше заголовка.  Это сторожит именно пару правил: вернуть прежнюю
жёсткую ширину полосы или убрать размер колонки нельзя молча.
"""

from __future__ import annotations

import re
from pathlib import Path

STYLE = Path(__file__).resolve().parents[1] / "web" / "static" / "player.css"
BASE_STYLE = Path(__file__).resolve().parents[1] / "web" / "static" / "style.css"


def _rule(sheet: Path, selector: str) -> str:
    found = re.search(rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", sheet.read_text(encoding="utf-8"))
    assert found is not None, f"в {sheet.name} нет правила {selector}"
    return found.group(1)


def test_preparing_column_keeps_the_old_minimum_and_accepts_the_title_width() -> None:
    body = _rule(STYLE, ".tc-preparing-body")

    assert re.search(r"display\s*:\s*grid", body)
    assert re.search(r"grid-template-columns\s*:\s*minmax\(35rem\s*,\s*max-content\)", body)


def test_preparing_bar_fills_that_shared_column() -> None:
    bar = _rule(BASE_STYLE, ".tc-preparing-bar")

    assert re.search(r"width\s*:\s*100%", bar)
