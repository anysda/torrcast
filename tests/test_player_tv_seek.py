"""A seek made outside the tab (card, Home Assistant, bridge) pulls the tab's film back on TV.

The tab hears such a seek only as a report, and a report behind the film read as a stale
tail: the TV went to 745.1 while the film stayed on 1062. The bridge numbers each of its
seeks in the snapshot (``seek``), and a new number arms the same pull as a press in the tab.
Real ``player.js`` in node, scenarios in ``tests/web_js/player_tv_seek.js``.

Rollback (``_follow`` ignores ``seek``): ``afterSeek`` stays on 1062.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "player_tv_seek.js"


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


def test_a_bridge_seek_back_moves_the_tab_film_to_the_tv(facts: dict[str, Any]) -> None:
    assert facts["beforeSeek"] == 1062
    assert facts["afterSeek"] == 745.1
    assert facts["seekingAfter"] is False


def test_without_a_new_seek_number_a_report_behind_the_film_is_a_tail(
    facts: dict[str, Any],
) -> None:
    assert facts["sameNumber"] == 760
    assert facts["noSeek"] == 760


def test_the_first_snapshot_of_a_cast_only_remembers_the_number(facts: dict[str, Any]) -> None:
    assert facts["firstSnapshot"] == 760
