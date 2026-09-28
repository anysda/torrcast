"""Год плитки стоит на карточке с первого кадра, а не после ответа сервера.

Первый ответ по согретой картине собирает тело целиком: круг поднимается с диска,
серии сверяются со справкой по эфиру. На живом стенде это 0.8 с, и всё это время
карточка стояла с именем и обложкой, но без года, хотя плитка знала его в миг клика.

Раскладка - в ``tests/web_js/card_shell_year.js``, сюда приезжают тексты скелета.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "card_shell_year.js"


@pytest.fixture(scope="module")
def stood() -> dict[str, list[list[str]]]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож скелета карточки исполняет card.js", pytrace=False)
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, list[list[str]]] = json.loads(done.stdout)
    return said


def test_the_skeleton_shows_the_year_the_tile_knew(stood: dict[str, list[list[str]]]) -> None:
    assert ["tc-title-detail", "Клиника"] in stood["fromTile"], stood["fromTile"]
    assert ["tc-meta", "2001"] in stood["fromTile"], (
        f"год плитки не встал в скелет, он ждёт ответа сервера: {stood['fromTile']}"
    )


def test_a_tile_without_a_year_draws_no_empty_year_line(
    stood: dict[str, list[list[str]]],
) -> None:
    assert not [row for row in stood["noYear"] if row[0] == "tc-meta"], stood["noYear"]
