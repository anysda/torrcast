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


def _prelude(tmp_path: Path, repo: Path | None = None) -> str:
    repo = repo or tmp_path
    return f"""
set -u
LANGUAGE=en
REPO_DIR={shlex.quote(str(repo))}
SELF={shlex.quote(str(repo / "install.sh"))}
LATE_LOG={shlex.quote(str(tmp_path / "late.log"))}
LATE_NOTES={shlex.quote(str(tmp_path / "notes"))}
LATE_PIDS={shlex.quote(str(tmp_path / "late.pids"))}
info() {{ printf 'INFO:%s\\n' "$1"; }}
late_run() {{{_body("late_run")}
}}
late_tree() {{{_body("late_tree")}
}}
orphan_late_jobs() {{{_body("orphan_late_jobs")}
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


def _install_sh(where: Path) -> Path:
    where.mkdir()
    # Like the late_run of a release before late.pids: on TERM its EXIT trap logs "done".
    script = (
        'trap \'sleep 0.5; echo "x | done: old" >> ../late.log\' EXIT\necho "$$" > pid\nsleep 300\n'
    )
    (where / "install.sh").write_text(script, encoding="utf-8")
    return where


def _pid(where: Path) -> int:
    deadline = time.monotonic() + 5
    while not (where / "pid").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return int((where / "pid").read_text(encoding="utf-8"))


@pytest.mark.machine
def test_an_upgrade_stops_the_retries_of_an_install_that_kept_no_pid_list(
    tmp_path: Path,
) -> None:
    """🔴 TC-1411. The install being replaced predates late.pids: its abandoned background
    work is found by directory; a foreign install.sh and one in the foreground live on."""
    ours, theirs, front = (_install_sh(tmp_path / n) for n in ("ours", "theirs", "front"))
    for where in (ours, theirs):
        subprocess.run(["bash", "-c", "(bash ./install.sh >/dev/null 2>&1 &)"], cwd=where)
    held = subprocess.Popen(["bash", "./install.sh"], cwd=front)
    pids: dict[Path, int] = {}
    try:
        pids.update({where: _pid(where) for where in (ours, theirs, front)})
        for repo in (ours, front):
            out = subprocess.run(
                ["bash", "-c", _prelude(tmp_path, repo) + "stop_late_jobs\n"],
                capture_output=True,
                text=True,
            )
            assert out.returncode == 0, out.stderr
        deadline = time.monotonic() + 5
        while _alive(pids[ours]) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not _alive(pids[ours])
        assert _alive(pids[theirs]) and _alive(pids[front])
        log = (tmp_path / "late.log").read_text(encoding="utf-8").splitlines()
        assert log[0] == "x | done: old"
        assert log[1:] == [
            log[-1].split(" | ")[0] + " | stopped, a newer ./install.sh started it over:"
            " the previous install's background work"
        ]
    finally:
        for pid in pids.values():
            subprocess.run(["pkill", "-P", str(pid)], capture_output=True)
            subprocess.run(["kill", str(pid)], capture_output=True)
        held.kill()
        held.wait()
