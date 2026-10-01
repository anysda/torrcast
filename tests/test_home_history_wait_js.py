"""Ряд «Продолжить» переспрашивается, пока сервер метит его «ещё наполняется»."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.machine
def test_continue_row_picks_up_covers_without_reload() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож ряда «Продолжить» исполняет home.js", pytrace=False)
    runner = Path(__file__).with_name("web_js") / "home_history_wait.js"
    done = subprocess.run([node, str(runner)], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    facts: dict[str, dict[str, object]] = json.loads(done.stdout)
    assert facts["api"] == {
        "marked": {"length": 1, "partial": True},
        "plain": {"length": 1, "partial": False},
    }, "обёртка сети потеряла метку «ещё наполняется»"
    filled, stuck, calm = facts["filled"], facts["stuck"], facts["calm"]
    assert filled["poster"] == "p1", "обложка, доехавшая после шторма, не встала в ряд"
    assert filled["asked"] == 3, "страница спрашивала историю и после снятой метки"
    assert filled["pauses"] == [2000]
    # Потолок 120 с: первый ответ и 60 переспросов через 2 с.
    assert stuck["asked"] == 61, "вечно неполный ряд держит опрос без потолка"
    assert calm["asked"] == 1, "ряд без метки переспрашивался зря"
    assert facts["twice"]["asked"] == 61, "второе ожидание при живом первом удвоило опрос"
