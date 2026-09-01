"""The installer keeps persistent macOS services in launchd."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).parents[1] / "install.sh").read_text(encoding="utf-8")


def _body(name: str) -> str:
    return SCRIPT.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]


def test_macos_services_use_persistent_launchd_jobs() -> None:
    run = _body("run_service")
    stop = _body("stop_service")
    write = _body("write_unit")
    bot = _body("setup_bot_unit")

    assert 'launchctl bootstrap system "/Library/LaunchDaemons/$label.plist"' in run
    assert 'launchctl bootout "system/org.torrcast.$1"' in stop
    # bootout is asynchronous: bootstrap of the same label right after it races the
    # teardown and the fresh registration is removed. Wait until the domain forgets.
    bootout = _body("launchd_bootout")
    assert 'launchd_bootout "$label"' in run
    assert 'launchctl print "system/$1"' in bootout
    assert 'path="/Library/LaunchDaemons/org.torrcast.$1.plist"' in write
    assert "<key>RunAtLoad</key><true/>" in write
    assert "<key>KeepAlive</key>" in write
    assert "<key>EnvironmentVariables</key>" in write
    assert "<key>StandardOutPath</key>" in write
    # launchd's default PATH lacks the Homebrew prefix; without carrying the
    # installer's PATH a `python3.11 ...` job dies with "not found".
    assert "<key>PATH</key><string>$path_xml</string>" in write
    # A literal \" inside the unquoted heredoc lands in the plist verbatim and
    # launchd refuses the job with a bare "Input/output error".
    plist = write.split("<<PLIST", 1)[1].split("\nPLIST", 1)[0]
    assert '\\"' not in plist
    bot_plist = "/Library/LaunchDaemons/org.torrcast.torrcast-bot.plist"
    assert f"launchctl bootstrap system {bot_plist}" in bot


def test_macos_does_not_claim_linux_only_guarantees() -> None:
    torrserver = _body("install_torrserver")
    shim = _body("setup_shim")

    assert 'place="disk $(ts_cache_disk)"' in torrserver
    assert "launchd has no enforceable memory ceiling" in torrserver
    marker = 'if [ "${OS_FAMILY:-linux}" = macos ]; then'
    macos_branch = torrserver.split(marker, 1)[1].split("fi", 1)[0]
    assert "MemoryMax" not in macos_branch
    assert 'if [ "${OS_FAMILY:-linux}" = macos ]; then' in shim
    assert "no socket activation" in shim
    assert "${knobs%$'\\n'Sockets=torrcast-shim.socket}" in shim


def test_macos_signs_prowlarr_adhoc() -> None:
    """Apple Silicon kills unsigned arm64 code at exec (OS_REASON_EXEC) before the
    service writes a single log line; the Prowlarr build ships unsigned."""
    binary = _body("install_prowlarr_binary")
    sign = _body("sign_macho_tree")

    assert 'sign_macho_tree "$PREFIX/prowlarr"' in binary
    assert "codesign --sign - --force" in sign
    assert "codesign -v" in sign
    assert "ad-hoc" in sign


def test_macos_phases_do_not_stop_after_the_binary() -> None:
    """The launchd port removes the stopgap early returns: a service phase that
    quits after unpacking the binary leaves the installer reporting success over
    a service that was never started."""
    for phase in ("install_torrserver", "install_prowlarr"):
        assert '[ "${OS_FAMILY:-linux}" != macos ] || return 0' not in _body(phase)
    assert "launchd services are not implemented yet" not in SCRIPT


def test_macos_disk_hls_cost_is_visible() -> None:
    hls = _body("setup_hls")

    assert 'HLS_DIR="${TORRCAST_HLS_DIR:-/var/tmp/torrcast}"' in SCRIPT
    assert "0.5-1.2 GiB" in hls


def test_macos_installs_no_trusted_root_and_relaxes_only_local_addresses() -> None:
    """No keychain trust on macOS; Prowlarr skips checks for local addresses only."""
    assert "add-trusted-cert" not in SCRIPT
    assert "delete-certificate" not in SCRIPT

    trust = _body("install_shim_trust")
    assert "the shim root is not trusted on macOS" in trust

    relax = _body("prowlarr_cert_relax")
    assert '[ "${OS_FAMILY:-linux}" = macos ] || return 0' in relax
    assert "disabledForLocalAddresses" in relax
    assert "Disabled<" not in relax
    # Prowlarr rewrites config.xml on every start and drops elements inserted from
    # outside; the setting must go through its own API to survive restarts.
    assert "/api/v1/config/host" in relax
    assert "sed_in_place" not in relax
    assert "stop_service" not in relax
    assert "indexers with public addresses are still verified" in relax

    prowlarr = _body("install_prowlarr")
    assert "    prowlarr_cert_relax\n" in prowlarr
    assert "<CertificateValidation>" not in prowlarr


def test_empty_arrays_survive_bash32_set_u() -> None:
    """Bash 3.2 (what macOS ships) calls an empty "${arr[@]}" unbound under set -u."""
    guarded = 'for name in ${CATALOG_PROMOTED[@]+"${CATALOG_PROMOTED[@]}"}; do'
    assert guarded in _body("catalog_promoted")
    assert '${keep[@]+"${keep[@]}"}' in SCRIPT
    assert '${pin[@]+"${pin[@]}"}' in _body("probe_whole")


def test_no_bare_variable_touches_multibyte_text() -> None:
    """Bash 3.2 (what macOS ships) glues the first byte of a following multibyte
    character to the variable name and dies with "unbound variable" under set -u."""
    offenders = [
        line
        for line in SCRIPT.splitlines()
        if re.search(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7f]", line)
    ]
    assert offenders == []


@pytest.mark.skipif(sys.platform != "darwin", reason="launchd persistence exists only on macOS")
def test_launchd_system_domain_is_reachable_on_macos() -> None:
    """Refuse on Linux: a text double cannot prove that launchd owns a process."""
    done = subprocess.run(
        ["launchctl", "print", "system"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert done.returncode == 0, done.stderr
