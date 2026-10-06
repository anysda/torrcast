"""Контракт отчёта позиции между настоящим browser API и сервером."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.machine
def test_browser_position_posts_its_payload_before_reading_the_reply() -> None:
    runner = Path(__file__).resolve().parent / "web_js" / "api_position.js"
    node = shutil.which("node")
    assert node is not None, "node не найден: нужен для исполнения настоящего api.js"
    done = subprocess.run(
        [node, str(runner)], capture_output=True, text=True, timeout=30, check=False
    )
    assert done.returncode == 0, done.stderr
    said = json.loads(done.stdout)

    assert said["calls"] == [
        {
            "url": "/api/web/position",
            "method": "POST",
            "body": {"key": "show-key", "phase": "playing", "pos": 41.25, "dur": 2587.512},
        }
    ]
    assert said["answer"] == {"code": 200, "finish": 2587.512}
