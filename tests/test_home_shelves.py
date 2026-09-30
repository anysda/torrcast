"""Холодная главная в node: плитки по мере прихода, «Грузим_» не врёт, опрос не бросается."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest


def _facts() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож главной исполняет home.js в node", pytrace=False)
    runner = Path(__file__).with_name("web_js") / "home_shelves.js"
    done = subprocess.run([node, str(runner)], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    facts: dict[str, Any] = json.loads(done.stdout)
    return facts


@pytest.mark.machine
def test_cold_home_shows_tiles_as_they_come_and_the_counter_means_both_shelves() -> None:
    facts = _facts()
    steps = facts["coldSteps"]
    assert [(step["fresh"], step["popular"]) for step in steps] == [
        (0, 0),
        (12, 0),
        (12, 0),
        (30, 4),
        (30, 30),
    ], "пришедшие плитки не встали на экран до конца сборки"
    assert steps[1]["skeleton"] and not steps[1]["empty"], "пустая пока полка написала «пока пусто»"
    assert [step["loading"] for step in steps] == [True, True, True, True, False], (
        "«Грузим_» погас до полных полок или завис после них"
    )
    assert facts["coldFinal"]["fresh"] == 29, "неиграющая плитка не сошла без перезагрузки"
    assert facts["coldAsked"] == 6
    assert facts["firstPause"] <= 1000


@pytest.mark.machine
def test_a_long_cold_build_is_waited_for_not_abandoned() -> None:
    facts = _facts()
    assert facts["slowAsked"] == 51, "опрос бросил сборку, не дождавшись полок"
    assert (facts["slowFinal"]["fresh"], facts["slowFinal"]["popular"]) == (2, 2)
    assert not facts["slowFinal"]["loading"]


@pytest.mark.machine
def test_the_shelves_do_not_wait_for_a_slow_history() -> None:
    facts = _facts()
    before, after = facts["lateBefore"], facts["lateAfter"]
    assert (before["fresh"], before["popular"]) == (3, 3), "полки ждали ответа истории"
    assert (before["continued"], before["waits"]) == (0, 1), "без истории нет скелета её ленты"
    assert (after["continued"], after["waits"]) == (1, 0), "история не встала на место скелета"
    assert (after["fresh"], after["popular"]) == (3, 3)
