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


def test_install_prowlarr_rewrites_a_broken_config() -> None:
    """A broken config.xml must be rewritten, not skipped, on the install path."""
    body = _body("install_prowlarr")
    assert "prowlarr_config_ok" in body
    assert "is unreadable" in body
