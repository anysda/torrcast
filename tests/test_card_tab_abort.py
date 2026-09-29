"""Вкладка сезона обрывает висящий добор прежней: настоящий ``card.js`` в node без браузера."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "card_tab_abort.js"


@pytest.fixture(scope="module")
def said() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож вкладки исполняет card.js", pytrace=False)
    done = subprocess.run([node, str(RUNNER)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)  # type: ignore[no-any-return]


def test_a_new_season_tab_cuts_the_request_the_previous_one_left_hanging(
    said: dict[str, Any],
) -> None:
    """«Рик и Морти»: брошенные вкладки держали соединения, и сезон 8 ждал строк 2 с."""
    assert said == {"aborted": True, "ended": True}
