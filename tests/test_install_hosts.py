"""Behaviour guards for installer-owned hosts entries and the Prowlarr catalog probe."""

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]
INSTALL = (REPO / "install.sh").read_text(encoding="utf-8")


def _body(name: str) -> str:
    return INSTALL.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]


def _functions(*names: str) -> str:
    return "\n".join(f"{name}() {{{_body(name)}\n}}" for name in names)


@pytest.mark.machine
def test_macos_catalog_pin_owns_both_loops_and_migrates_the_old_line(tmp_path: Path) -> None:
    """The old naked IPv4 pin is upgraded, and a rerun is byte-for-byte idle."""
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n127.0.0.1 indexers.prowlarr.com\n", encoding="utf-8")
    script = f"""
set -euo pipefail
{_functions("hosts_pin")}
pick_python() {{ PYTHON={shlex.quote(sys.executable)}; }}
skip() {{ :; }}
info() {{ :; }}
OS_FAMILY=macos
TORRCAST_FLUSH_DNS=none
HOSTS_FILE={shlex.quote(str(hosts))}
REPO_DIR={shlex.quote(str(REPO))}
hosts_pin indexers.prowlarr.com
before=$(cat "$HOSTS_FILE")
hosts_pin indexers.prowlarr.com
[ "$before" = "$(cat "$HOSTS_FILE")" ]
"""
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)

    assert done.returncode == 0, done.stderr
    assert hosts.read_text(encoding="utf-8") == (
        "127.0.0.1 localhost\n"
        "127.0.0.1 indexers.prowlarr.com # torrcast-shim\n"
        "::1 indexers.prowlarr.com # torrcast-shim\n"
    )


@pytest.mark.machine
def test_catalog_decision_bypasses_hosts_and_can_change_between_runs() -> None:
    """A stale pin cannot freeze yesterday's unavailable verdict."""
    script = f"""
set -euo pipefail
{_functions("catalog_available", "prepare_definitions")}
PL_DEFS_URL=https://indexers.prowlarr.com/master/11
shim_resolve() {{ printf '192.0.2.10 2001:db8::10'; }}
probe_every() {{
    printf 'probe=%s %s addresses=%s\n' "$1" "$2" "$4"
    [ "$AVAILABLE" = 1 ]
}}
info() {{ printf '%s\n' "$1"; }}
hosts_pin() {{ printf 'pin=%s\n' "$1"; }}
job_start() {{ printf 'job=%s\n' "$1"; }}
AVAILABLE=1 prepare_definitions
AVAILABLE=0 prepare_definitions
"""
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)

    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        "probe=indexers.prowlarr.com /master/11 addresses=192.0.2.10 2001:db8::10",
        "Prowlarr indexer catalog is available - it will fetch definitions itself",
        "probe=indexers.prowlarr.com /master/11 addresses=192.0.2.10 2001:db8::10",
        "⚠ Prowlarr indexer catalog is unavailable - fetching definitions from GitHub",
        "pin=indexers.prowlarr.com",
        "job=defs",
    ]
