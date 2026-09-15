"""Стрелка вниз с поля поиска: настоящий ``nav.js`` в node на прямоугольниках экрана.

Сбой посреди поиска оставляет плитки, и кнопка повтора стоит между полем и ними у левого
края. Раскладка лежит в ``tests/web_js/nav.js``, сюда приезжает только имя места под фокусом.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "nav.js"


@pytest.fixture(scope="module")
def landed() -> dict[str, str | None]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож пульта исполняет nav.js в node", pytrace=False)
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, str | None] = json.loads(done.stdout)
    return said


def test_down_from_the_search_field_reaches_try_again_above_kept_tiles(
    landed: dict[str, str | None],
) -> None:
    assert landed["failed"] == "retry", f"стрелка вниз с поля встала на {landed['failed']}"


def test_down_from_the_search_field_still_lands_on_the_middle_of_the_first_row(
    landed: dict[str, str | None],
) -> None:
    assert landed["results"] in {"tile3", "tile4"}, f"стрелка вниз встала на {landed['results']}"
