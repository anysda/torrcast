"""Guards for Prowlarr config.xml integrity on the install path (TC-1410)."""

import shlex
import subprocess
from pathlib import Path

REPO = Path(__file__).parents[1]
INSTALL = (REPO / "install.sh").read_text(encoding="utf-8")


def _body(name: str) -> str:
    return INSTALL.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]


def _functions(*names: str) -> str:
    return "\n".join(f"{name}() {{{_body(name)}\n}}" for name in names)


def _verdict(path: Path) -> int:
    script = f"""
set -u
{_functions("prowlarr_config_ok")}
prowlarr_config_ok {shlex.quote(str(path))}
"""
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True).returncode


def test_whole_config_passes(tmp_path: Path) -> None:
    cfg = tmp_path / "config.xml"
    cfg.write_text("<Config>\n  <Port>9696</Port>\n</Config>\n", encoding="utf-8")
    assert _verdict(cfg) == 0


def test_all_nul_config_is_rejected(tmp_path: Path) -> None:
    """The classic leftover: a file of NUL bytes that still passes `[ -f ]`."""
    cfg = tmp_path / "config.xml"
    cfg.write_bytes(b"\x00" * 512)
    assert _verdict(cfg) != 0


def test_config_with_embedded_nul_is_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "config.xml"
    cfg.write_bytes(b"<Config>\x00<Port>9696</Port></Config>\n")
    assert _verdict(cfg) != 0


def test_truncated_config_without_closing_tag_is_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "config.xml"
    cfg.write_text("<Config>\n  <Port>9696</Port>\n", encoding="utf-8")
    assert _verdict(cfg) != 0


def _config_block() -> str:
    body = _body("install_prowlarr")
    start = body.index('    if [ -f "$PREFIX/prowlarr-data/config.xml" ] && prowlarr_config_ok')
    return body[start:].split("\n    run_service prowlarr", 1)[0]


def _rewrite(prefix: Path) -> str:
    script = f"""
set -u
PREFIX={shlex.quote(str(prefix))}
PL_HOST=127.0.0.1
PL_PORT=9696
skip() {{ echo SKIP; }}
loud() {{ echo "LOUD:$1"; }}
final_loud() {{ echo "FINAL:$1"; }}
stop_service() {{ echo "STOP:$1"; }}
{_functions("prowlarr_config_ok")}
{_config_block()}
"""
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_a_zeroed_config_is_rewritten_and_the_hung_prowlarr_stopped(tmp_path: Path) -> None:
    """Prowlarr hangs on a NUL config instead of exiting, so systemd keeps it active and
    `enable --now` never restarts it: the rewrite must stop the service first."""
    (tmp_path / "prowlarr-data").mkdir()
    cfg = tmp_path / "prowlarr-data" / "config.xml"
    cfg.write_bytes(b"\x00" * 453)
    out = _rewrite(tmp_path)
    # repeated after the summary: under the TUI a plain loud line stays in the log
    assert "FINAL:Prowlarr config.xml at" in out and "is unreadable" in out
    assert "STOP:prowlarr" in out
    assert _verdict(cfg) == 0


def test_a_whole_config_is_kept_and_prowlarr_left_running(tmp_path: Path) -> None:
    (tmp_path / "prowlarr-data").mkdir()
    cfg = tmp_path / "prowlarr-data" / "config.xml"
    cfg.write_text("<Config>\n  <ApiKey>k</ApiKey>\n</Config>\n", encoding="utf-8")
    out = _rewrite(tmp_path)
    assert out.strip() == "SKIP"
    assert "<ApiKey>k</ApiKey>" in cfg.read_text(encoding="utf-8")
