"""Esc на карточке - тот же выход, что кнопка «Назад» (TC-1335).

Настоящий ``card.js`` в node, слушатель клавиатуры проверяется без разметки экрана.
Раскладка - в ``tests/web_js/card_escape.js``, сюда приезжают только счётчики вызовов.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "card_escape.js"


@pytest.fixture(scope="module")
def pressed() -> dict[str, int]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож Esc-карточки исполняет card.js в node", pytrace=False)
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, int] = json.loads(done.stdout)
    return said


def test_escape_on_the_card_page_goes_back_like_the_button(pressed: dict[str, int]) -> None:
    assert pressed["onCard"] == 1, f"Esc на карточке не позвал history.back(): {pressed}"


def test_escape_elsewhere_does_not_touch_the_cards_own_history(pressed: dict[str, int]) -> None:
    assert pressed["onHome"] == 0, f"Esc вне карточки дёрнул history.back(): {pressed}"
    assert pressed["onPlay"] == 0, f"Esc на /play через слушатель карточки: {pressed}"
