"""Сторож следов среды разработки в публичном дереве."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

GATE = Path(__file__).parents[1] / "scripts" / "public_tree_gate.py"


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), str(root)],
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.machine
def test_the_real_tracked_tree_is_clean() -> None:
    result = _run(Path(__file__).parents[1])

    assert result.returncode == 0, result.stderr


@pytest.mark.machine
def test_a_tracked_development_trace_turns_the_gate_red(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    sample = tmp_path / "sample.txt"
    sample.write_text("receiver=" + "192" + ".168.1.104\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "sample.txt"], check=True)

    red = _run(tmp_path)

    assert red.returncode == 1
    assert red.stderr.splitlines()[0] == "публичное дерево содержит следы среды разработки:"
    assert "sample.txt:1: адрес домашней сети" in red.stderr

    sample.write_text("receiver=192.0.2.104\n", encoding="utf-8")
    green = _run(tmp_path)
    assert green.returncode == 0
    assert green.stdout.startswith("публичное дерево чисто:")
