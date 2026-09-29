"""An episode row pressed before the card knew its release: real ``card.js`` in node."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "card_early_press.js"


@pytest.fixture(scope="module")
def pressed() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node is missing: the early press runs card.js", pytrace=False)
    done = subprocess.run([node, str(RUNNER)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)  # type: ignore[no-any-return]


def test_a_press_left_behind_does_not_start_the_episode_on_the_next_visit(
    pressed: dict[str, Any],
) -> None:
    assert pressed["back"] == {"clicks": 0, "kept": False}


def test_the_full_body_plays_the_pressed_row_once(pressed: dict[str, Any]) -> None:
    assert pressed["plays"] == {"clicks": 1, "kept": False}


@pytest.mark.parametrize("outcome", ["grey", "refused"])
def test_a_grey_row_or_a_refusal_ends_the_press_as_a_click_on_the_full_card_would(
    pressed: dict[str, Any], outcome: str
) -> None:
    # Nothing is kept for a later body: a press that waited would start the episode by itself.
    assert pressed[outcome] == {"clicks": 0, "kept": False}


@pytest.mark.parametrize("outcome", ["searching", "other"])
def test_the_press_waits_for_the_full_body_of_its_own_card(
    pressed: dict[str, Any], outcome: str
) -> None:
    assert pressed[outcome] == {"clicks": 0, "kept": True}
