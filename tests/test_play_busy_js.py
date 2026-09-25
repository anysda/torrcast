"""409 запуска на настоящих ``api.js`` и ``card.js`` читается человеком."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "play_busy.js"


@pytest.fixture(scope="module")
def screen() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож 409 исполняет api.js и card.js", pytrace=False)
    done = subprocess.run([node, str(RUNNER)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)  # type: ignore[no-any-return]


def test_play_busy_is_written_on_the_button_instead_of_being_dropped(
    screen: dict[str, Any],
) -> None:
    assert screen["button"] == "Показ уже запускается"
    assert screen["routes"] == [], "отказ не должен открывать плеер нового показа"
    assert screen["dropped"] == 1, "старый ящик вкладки остался взведён после отказа"


def test_the_refusal_word_gives_the_button_and_the_episode_row_back(
    screen: dict[str, Any],
) -> None:
    assert screen["buttonLater"] == "Играть", "кнопка навсегда осталась словом отказа"
    assert screen["rowSaid"] == "Показ уже запускается"
    assert screen["rowLater"] == ["3", "Сезон 1 · 3", "0:42:00"], "строка серии стёрта отказом"


def test_cast_busy_is_written_on_its_button_too(screen: dict[str, Any]) -> None:
    assert screen["cast"] == {"ok": False, "error": "busy"}
    assert screen["castWord"] == "Показ уже запускается"
