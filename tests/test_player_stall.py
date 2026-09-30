"""A stall after the first frame shows buffering only once it outlasts ``STALL_SHOW_MS``.

A seek to position and a segment seam give ``waiting`` for 20-80 ms, and «Buffering_»
flashed for a frame or two over a running film. Real ``player.js`` in node, scenarios in
``tests/web_js/player_stall.js``; the screen is read every 10 ms of virtual time.

Rollback (``waiting`` shows the screen at once): ``short`` and ``edge`` are seen at 0 ms.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "player_stall.js"


@pytest.fixture(scope="module")
def facts() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node is missing: the scenarios run player.js in node", pytrace=False)
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, Any] = json.loads(done.stdout)
    return said


def test_the_threshold_sits_between_a_seek_blink_and_a_visible_pause(
    facts: dict[str, Any],
) -> None:
    assert 80 * 3 <= facts["threshold"] <= 500, facts["threshold"]


def test_a_short_stall_never_shows_buffering(facts: dict[str, Any]) -> None:
    assert facts["short"] is None, f"a seek blink showed buffering at {facts['short']} ms"
    assert facts["edge"] is None, f"a stall just under the threshold flashed at {facts['edge']} ms"


def test_a_long_stall_shows_buffering_at_the_threshold(facts: dict[str, Any]) -> None:
    assert facts["long"] == facts["threshold"], facts


def test_a_pause_inside_a_stall_does_not_cover_the_frame(facts: dict[str, Any]) -> None:
    assert facts["paused"] is None, facts
