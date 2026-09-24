"""Предусловие ffmpeg: одна причина до дорогого интеграционного набора."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
CHECK = ROOT / "scripts" / "ffmpeg-gate"
FULL_GATE = ROOT / "scripts" / "test-gate"
INSTALL = ROOT / "install.sh"


def _minimum() -> str:
    match = re.search(r'^FFMPEG_MIN="\$\{TORRCAST_FFMPEG_MIN:-(.+)\}"$', INSTALL.read_text(), re.M)
    assert match is not None
    return match.group(1)


def _path(tmp_path: Path, versions: dict[str, str]) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    sed = shutil.which("sed")
    assert sed is not None
    (bin_dir / "sed").symlink_to(sed)
    for name, version in versions.items():
        binary = bin_dir / name
        binary.write_text(
            f"#!/bin/sh\nprintf '%s\\n' '{name} version {version} Copyright'\n",
            encoding="utf-8",
        )
        binary.chmod(0o755)
    return bin_dir


def _run(check: Path, bin_dir: Path, *, full: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    if full:
        env["TORRCAST_GATE_MODE"] = "unscoped"
    return subprocess.run(
        [str(check)], cwd=ROOT, env=env, text=True, capture_output=True, check=False
    )


def _failure(ffmpeg: str, ffprobe: str) -> str:
    minimum = _minimum()
    return (
        f"гейт: нужны ffmpeg и ffprobe ≥ {minimum} (-readrate_initial_burst); "
        f"найдено: ffmpeg {ffmpeg}, ffprobe {ffprobe}; установи через ./install.sh\n"
    )


def test_old_ffmpeg_stops_the_sewn_full_gate_with_one_reason(tmp_path: Path) -> None:
    """Сшитый гейт отказывает до стадий: ни один набор ещё не был запущен."""
    bin_dir = _path(tmp_path, {"ffmpeg": "5.1.9", "ffprobe": "5.1.9"})
    date = shutil.which("date")
    assert date is not None
    (bin_dir / "date").symlink_to(date)

    done = _run(FULL_GATE, bin_dir, full=True)

    assert done.returncode != 0
    assert done.stdout == ""
    assert done.stderr == _failure("5.1.9", "5.1.9")


def test_missing_ffmpeg_and_ffprobe_are_a_red_reason(tmp_path: Path) -> None:
    done = _run(CHECK, _path(tmp_path, {}))

    assert done.returncode != 0
    assert done.stdout == ""
    assert done.stderr == _failure("нет", "нет")


@pytest.mark.parametrize(("ffmpeg", "ffprobe"), [("6.1", "5.1.9"), ("5.1.9", "6.1")])
def test_either_old_binary_rejects_the_pair(ffmpeg: str, ffprobe: str, tmp_path: Path) -> None:
    versions = {"ffmpeg": ffmpeg, "ffprobe": ffprobe}
    done = _run(CHECK, _path(tmp_path, versions))

    assert done.returncode != 0
    assert done.stderr == _failure(ffmpeg, ffprobe)


@pytest.mark.parametrize("version", ["6.1", "n7.1", "7.1.1-static", "N-117000-gdeadbeef"])
def test_supported_version_forms_pass(version: str, tmp_path: Path) -> None:
    done = _run(CHECK, _path(tmp_path, {"ffmpeg": version, "ffprobe": version}))

    assert done.returncode == 0, done.stderr
    assert done.stdout == ""
    assert done.stderr == ""


def test_the_minimum_has_one_source_and_the_full_gate_calls_the_check() -> None:
    check = CHECK.read_text(encoding="utf-8")
    gate = FULL_GATE.read_text(encoding="utf-8")

    assert _minimum() not in check
    assert gate.index("scripts/ffmpeg-gate") < gate.index('stage "ffmpeg-овый набор"')
