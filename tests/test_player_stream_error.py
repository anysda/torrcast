"""A stream error shows buffering while the tape is rebuilt, not a frozen frame.

A decoder failure gives no ``waiting``: before this the frame stood still through every
retry while the tape under it dropped to zero (Chromium, ``MEDIA_ERR_DECODE``, «Оно» 2017
from the bookmark). Real ``player.js`` in node, scenarios in ``tests/web_js/player_error.js``.

Rollback (no ``_screenBuffering`` in ``_onStreamError``): ``buffering`` is ``None``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "player_error.js"


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


def test_a_stream_error_shows_buffering_before_the_retry(facts: dict[str, Any]) -> None:
    assert facts["buffering"] is not None and facts["buffering"] < 1000, facts


def test_the_buffering_screen_leaves_once_the_tape_plays(facts: dict[str, Any]) -> None:
    assert facts["cleared"], facts


def test_the_fourth_error_still_ends_on_the_lost_screen(facts: dict[str, Any]) -> None:
    assert facts["lost"], facts
