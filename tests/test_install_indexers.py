"""Install-path guards for the reference manifest and the final-screen roll call (TC-1411)."""

import json
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]
INSTALL = (REPO / "install.sh").read_text(encoding="utf-8")


def _body(name: str) -> str:
    return INSTALL.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]


def _bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True)


def _run_name_absent(
    tmp_path: Path, manifest: object, live: object, pending: tuple[str, ...] = ()
) -> str:
    """Run name_absent_reference_indexers with stubbed curl + a stub final_loud.

    final_loud is replaced by an echo so the test reads exactly the named line; curl
    is a shell function returning the live Prowlarr list from a file.
    """
    state = tmp_path / "state"
    state.mkdir()
    (state / "indexers.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "live.json").write_text(json.dumps(live), encoding="utf-8")
    script = f"""
set -u
STATE_DIR={shlex.quote(str(state))}
PL_URL=http://127.0.0.1:9696
curl() {{ cat {shlex.quote(str(tmp_path / "live.json"))}; }}
final_loud() {{ printf 'FINAL_EN:%s\\n' "$1"; }}
name_absent_reference_indexers() {{{_body("name_absent_reference_indexers")}
}}
name_absent_reference_indexers deadbeef {" ".join(shlex.quote(n) for n in pending)}
"""
    out = _bash(script)
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is required on the install host")
def test_absent_reference_indexers_are_named_on_the_final_screen(tmp_path: Path) -> None:
    manifest = [{"name": "RuTor"}, {"name": "RuTor names"}, {"name": "sukebei"}, {"name": "yts"}]
    live = [{"name": "yts"}]
    out = _run_name_absent(tmp_path, manifest, live)
    assert out.startswith("FINAL_EN:")
    assert "indexers not set up yet" in out
    for missing in ("RuTor", "RuTor names", "sukebei"):
        assert missing in out
    assert "yts" not in out.split(":", 1)[1]  # the one that is present is not named


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is required on the install host")
def test_a_full_prowlarr_prints_nothing(tmp_path: Path) -> None:
    """Every reference indexer present: the final screen stays silent."""
    manifest = [{"name": "RuTor"}, {"name": "sukebei"}]
    live = [{"name": "RuTor"}, {"name": "sukebei"}]
    assert _run_name_absent(tmp_path, manifest, live) == ""


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is required on the install host")
def test_indexers_still_arriving_in_the_background_are_not_named(tmp_path: Path) -> None:
    """The late ones are being added right now: naming them would warn on every healthy run."""
    manifest = [{"name": "RuTor"}, {"name": "YTS"}, {"name": "RuTor names"}]
    out = _run_name_absent(tmp_path, manifest, [], pending=("YTS", "RuTor names"))
    assert out.startswith("FINAL_EN:indexers not set up yet: RuTor - "), out


def test_a_silent_prowlarr_is_not_fatal(tmp_path: Path) -> None:
    """curl failing (Prowlarr down) returns 0 and names nothing: the install still ends."""
    state = tmp_path / "state"
    state.mkdir()
    (state / "indexers.json").write_text('[{"name": "RuTor"}]', encoding="utf-8")
    script = f"""
set -u
STATE_DIR={shlex.quote(str(state))}
PL_URL=http://127.0.0.1:9696
curl() {{ return 7; }}
final_loud() {{ printf 'FINAL_EN:%s\\n' "$1"; }}
name_absent_reference_indexers() {{{_body("name_absent_reference_indexers")}
}}
name_absent_reference_indexers deadbeef
"""
    out = _bash(script)
    assert out.returncode == 0 and out.stdout == ""


def test_install_indexers_writes_the_manifest_atomically() -> None:
    body = _body("install_indexers")
    assert 'manifest+=("$body")' in body
    assert "indexers.json.tmp" in body and 'mv "$STATE_DIR/indexers.json.tmp"' in body
    assert "name_absent_reference_indexers" in body


def test_the_reconciler_is_wired_into_the_install() -> None:
    reconcile = _body("setup_reconcile")
    assert "indexer-reconcile.py" in reconcile
    assert "TORRCAST_INDEXER_MANIFEST=$STATE_DIR/indexers.json" in reconcile
    assert "setup_reconcile" in _body("install_indexers")  # inside the phase worker


def _run_setup_reconcile(tmp_path: Path) -> str:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "indexer-reconcile.py").write_text("new\n", encoding="utf-8")
    prefix = tmp_path / "opt"
    prefix.mkdir()
    (prefix / "indexer-reconcile.py").write_text("old\n", encoding="utf-8")
    script = f"""
set -u
unset TORRCAST_NO_SYSTEMD
REPO_DIR={shlex.quote(str(repo))}
PREFIX={shlex.quote(str(prefix))}
STATE_DIR=/nonexistent
PL_URL=http://127.0.0.1:9696
PYTHON=python3
INDEXER_RETRY_TIMES=1
INDEXER_RETRY_EVERY=1
RECONCILE_EVERY=1
log() {{ :; }}
skip() {{ echo SKIP; }}
info() {{ :; }}
pick_python() {{ :; }}
stop_service() {{ echo "STOP:$1"; }}
run_service() {{ echo "RUN:$1"; }}
install() {{ echo INSTALL; command install "$@"; }}
setup_reconcile() {{{_body("setup_reconcile")}
}}
setup_reconcile
"""
    out = _bash(script)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_new_reconciler_code_stops_the_running_one_before_it_is_replaced(
    tmp_path: Path,
) -> None:
    """An unchanged unit is not restarted by `enable --now`: without the stop the old
    reconciler would keep running the previous code until a reboot."""
    out = _run_setup_reconcile(tmp_path).split()
    assert out == ["STOP:torrcast-reconcile", "INSTALL", "RUN:torrcast-reconcile"], out
    assert (tmp_path / "opt" / "indexer-reconcile.py").read_text(encoding="utf-8") == "new\n"


def test_the_reconciler_waits_for_the_retry_ladder_and_skips_the_sandbox() -> None:
    reconcile = _body("setup_reconcile")
    assert "TORRCAST_RECONCILE_DELAY=$((INDEXER_RETRY_TIMES * INDEXER_RETRY_EVERY))" in reconcile
    sandbox = reconcile.index("TORRCAST_NO_SYSTEMD")
    assert sandbox < reconcile.index("run_service"), "the sandbox must not start the daemon"


def _catalog_verdict() -> str:
    start = INSTALL.index('    if [ -n "$CATALOG_CUT_EN" ]; then')
    return INSTALL[start:].split("\n    fi\n", 1)[0] + "\n    fi\n"


def test_a_cut_catalog_is_repeated_after_the_summary() -> None:
    """Under the TUI a plain loud line ends up in the log only: the last screen said
    "[OK] installed successfully" with rc=2 and no word about the cut role."""
    script = f"""
set -u
CATALOG_CUT_EN="western releases and anime - Knaben (not added)"
CATALOG_CUT_RU="x"
EXIT_CATALOG_CUT=2
loud() {{ :; }}
info() {{ :; }}
final_loud() {{ printf 'FINAL_EN:%s\\n' "$1"; }}
{_catalog_verdict()}
"""
    out = _bash(script)
    assert out.returncode == 2, out.stderr
    assert "FINAL_EN:catalog is incomplete: western releases and anime - Knaben" in out.stdout
