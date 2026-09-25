"""Вкладка сезона на раздаче всех сезонов: настоящий ``card.js`` в node без браузера."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "card_season_answer.js"


@pytest.fixture(scope="module")
def redraws() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож вкладки исполняет card.js", pytrace=False)
    done = subprocess.run([node, str(RUNNER)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)  # type: ignore[no-any-return]


def test_a_season_tab_answer_equal_to_the_body_still_draws_the_rows(
    redraws: dict[str, Any],
) -> None:
    assert redraws["tab"] == 1, "вкладка сняла строки, а равный ответ их не вернул"


def test_a_plain_reload_with_the_same_answer_leaves_the_body_alone(
    redraws: dict[str, Any],
) -> None:
    assert redraws["reload"] == 0
