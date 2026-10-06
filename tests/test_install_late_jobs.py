"""A rerun of install.sh stops the previous install's background work (TC-1411)."""

import shlex
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]
INSTALL = (REPO / "install.sh").read_text(encoding="utf-8")


def _body(name: str) -> str:
    return INSTALL.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]


def _prelude(tmp_path: Path) -> str:
    return f"""
set -u
LANGUAGE=en
LATE_LOG={shlex.quote(str(tmp_path / "late.log"))}
LATE_NOTES={shlex.quote(str(tmp_path / "notes"))}
LATE_PIDS={shlex.quote(str(tmp_path / "late.pids"))}
info() {{ printf 'INFO:%s\\n' "$1"; }}
late_run() {{{_body("late_run")}
}}
late_tree() {{{_body("late_tree")}
}}
stop_late_jobs() {{{_body("stop_late_jobs")}
}}
"""


def _alive(pid: int) -> bool:
    return subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode == 0


@pytest.mark.machine
def test_a_rerun_stops_the_previous_retry_and_its_children(tmp_path: Path) -> None:
    """The old ladder lived its hour beside the new one: two asks at one tracker, and
    401s in late.log from the Prowlarr key the rerun had replaced."""
    started = subprocess.run(
        ["bash", "-c", _prelude(tmp_path) + "ladder() { sleep 300; }\nlate_run a a ladder\n"],
        capture_output=True,
        text=True,
    )
    assert started.returncode == 0, started.stderr
    row = (tmp_path / "late.pids").read_text(encoding="utf-8").split("\t")
    pid = int(row[0])
    assert row[2].strip() == "ladder" and row[1]
    time.sleep(0.3)
    child = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout
    assert child.strip(), "the retry must be waiting in its sleep"
    stopped = subprocess.run(
        ["bash", "-c", _prelude(tmp_path) + "stop_late_jobs\n"], capture_output=True, text=True
    )
    assert "INFO:stopped the previous install's background work" in stopped.stdout
    deadline = time.monotonic() + 5
    while (_alive(pid) or _alive(int(child.split()[0]))) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _alive(pid) and not _alive(int(child.split()[0]))
    log = (tmp_path / "late.log").read_text(encoding="utf-8")
    assert "stopped, a newer ./install.sh started it over: a" in log
    assert "FAILED" not in log
    assert not (tmp_path / "late.pids").exists()


@pytest.mark.machine
def test_a_reused_pid_is_not_killed(tmp_path: Path) -> None:
    """After a reboot the same pid may belong to someone else: the start time tells them apart."""
    stranger = subprocess.Popen(["sleep", "30"])
    try:
        (tmp_path / "late.pids").write_text(
            f"{stranger.pid}\tMon Jan  1 00:00:00 2001\tretry_add_indexers\n", encoding="utf-8"
        )
        out = subprocess.run(
            ["bash", "-c", _prelude(tmp_path) + "stop_late_jobs\n"], capture_output=True, text=True
        )
        assert out.returncode == 0 and out.stdout == ""
        assert stranger.poll() is None
    finally:
        stranger.kill()
        stranger.wait()


def test_the_rerun_stops_old_work_before_anything_else() -> None:
    main = _body("main")
    assert main.index("stop_late_jobs") < main.index("job_start")
