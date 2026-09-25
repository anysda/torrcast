"""Живое состояние плашки главной исполняется настоящими ``app.js`` и ``home.js``."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "home_state.js"
START = "NOW PLAYING ▶ / ВАСАБИ / 50:51 / 1:33:50"


@pytest.fixture(scope="module")
def facts() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail(
            "node не найден: сторож состояния главной исполняет home.js в node, поставь nodejs",
            pytrace=False,
        )
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=30, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, Any] = json.loads(done.stdout)
    return said


@pytest.mark.machine
@pytest.mark.parametrize("name", ["removed", "ended"])
def test_a_show_that_stops_loses_the_home_badge(facts: dict[str, Any], name: str) -> None:
    seen = facts[name]["seen"]
    assert seen["+0"] == START
    assert [seen["+5"], seen["+10"], seen["+20"]] == ["", "", ""]


@pytest.mark.machine
def test_a_show_started_elsewhere_appears_and_keeps_moving(facts: dict[str, Any]) -> None:
    started = facts["started"]
    assert started["seen"] == {
        "+0": "",
        "+5": "NOW PLAYING ▶ / ВАСАБИ / 50:55 / 1:33:50",
        "+10": "NOW PLAYING ▶ / ВАСАБИ / 51:01 / 1:33:50",
        "+20": "NOW PLAYING ▶ / ВАСАБИ / 51:11 / 1:33:50",
    }
    assert started["opens"] == 1, "живая плашка перестала вести на показ"


@pytest.mark.machine
def test_a_live_show_stays_visible_and_its_clock_moves(facts: dict[str, Any]) -> None:
    seen = facts["live"]["seen"]
    assert seen["+0"] == START
    assert len(set(seen.values())) == len(seen), "время живого показа замерло"
    assert facts["live"]["opens"] == 1


@pytest.mark.machine
def test_a_hidden_home_tab_does_not_poll_the_server(facts: dict[str, Any]) -> None:
    hidden = facts["hidden"]
    assert hidden["callsWhileHidden"] == 1
    assert hidden["callsAfterVisible"] == 2
    assert hidden["line"] == "NOW PLAYING ▶ / ВАСАБИ / 51:13 / 1:33:50"
