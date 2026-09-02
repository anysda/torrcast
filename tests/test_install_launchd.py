"""The installer keeps persistent macOS services in launchd."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "install.sh"
SCRIPT = SCRIPT_PATH.read_text(encoding="utf-8")


def _body(name: str) -> str:
    return SCRIPT.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]


def test_macos_services_use_persistent_launchd_jobs() -> None:
    run = _body("run_service")
    stop = _body("stop_service")
    write = _body("write_unit")
    bot = _body("setup_bot_unit")

    assert 'launchctl bootstrap system "/Library/LaunchDaemons/$label.plist"' in run
    assert 'launchd_bootout "org.torrcast.$1"' in stop
    # bootout is asynchronous: bootstrap of the same label right after it races the
    # teardown and the fresh registration is removed. Wait until the domain forgets.
    bootout = _body("launchd_bootout")
    assert 'launchd_bootout "$label"' in run
    assert 'launchctl print "system/$1"' in bootout
    assert '[ "$i" -ge 180 ]' in bootout
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


@pytest.mark.machine
def test_stop_then_run_waits_for_async_bootout_and_loads_the_job(tmp_path: Path) -> None:
    """launchd reports a booted-out job once more before removing it. The installer
    must wait for that removal and must not mistake an unchanged plist for a live job."""
    launchctl = tmp_path / "launchctl"
    launchctl.write_text(
        """#!/bin/sh
state="$LAUNCHD_STATE"
case "$1" in
    bootout)
        [ -f "$state/loaded" ] && : >"$state/pending"
        exit 0
        ;;
    print)
        if [ -f "$state/pending" ]; then
            rm -f "$state/pending" "$state/loaded"
            exit 0
        fi
        [ -f "$state/loaded" ]
        ;;
    bootstrap)
        : >"$state/loaded"
        ;;
esac
""",
        encoding="utf-8",
    )
    launchctl.chmod(0o755)
    (tmp_path / "loaded").touch()
    functions = "\n".join(
        f"{name}() {{{_body(name)}\n}}"
        for name in ("run_service", "launchd_bootout", "stop_service")
    )
    script = f"""
set -u
PATH={shlex.quote(str(tmp_path))}:$PATH
LAUNCHD_STATE={shlex.quote(str(tmp_path))}
OS_FAMILY=macos
PREFIX={shlex.quote(str(tmp_path))}
export PATH LAUNCHD_STATE OS_FAMILY PREFIX
quoted_knobs() {{ printf '%s' "$1"; }}
write_unit() {{ return 1; }}
skip() {{ printf 'already in place: %s\n' "$1"; }}
sleep() {{ :; }}
{functions}
stop_service prowlarr ignored
run_service prowlarr description command
launchctl print system/org.torrcast.prowlarr
"""
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)

    shown = done.stdout + done.stderr
    assert done.returncode == 0, shown
    assert (tmp_path / "loaded").exists(), shown
    assert "already in place" not in shown


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
    assert "Environment=TORRCAST_FLUSH_DNS=macos" in shim
    assert "Environment=TORRCAST_DNS_FALLBACK=1.1.1.1,9.9.9.9" in shim
    assert "Environment=TORRCAST_PIN_ADDRESSES=127.0.0.1,::1" in shim
    assert "Environment=TORRCAST_LISTEN_IPV6=1" in shim


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


def test_macos_cast_is_a_root_rexec_wrapper_not_a_symlink() -> None:
    """macOS grants local-network access per "responsible process" and an unsigned
    launchd job has none (Errno 65); root is outside TCC entirely. So on a Mac the
    show runs as root, and `cast` in PATH is a wrapper that re-execs itself through
    `sudo -n` - never a symlink a regular user would follow into permission errors.
    Linux keeps the plain symlink: its whole tract already works as root."""
    body = _body("install_cast_command")
    linux = body.split('if [ "${OS_FAMILY:-linux}" != macos ]; then', 1)[1].split("return 0", 1)[0]
    macos = body.split("return 0", 1)[1]

    assert 'ln -sfn "$PREFIX/venv/bin/cast" "$BIN_DIR/cast"' in linux
    assert "ln -sfn" not in macos
    assert 'exec /usr/bin/sudo -n $BIN_DIR/cast "\\$@"' in macos
    # sudo cuts PATH to /usr/bin:/bin:... and the Homebrew ffmpeg/ffprobe vanish;
    # the wrapper sets PATH itself once it is root (sudo VAR=... needs SETENV).
    assert 'PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"' in macos
    assert 'exec $PREFIX/venv/bin/cast "\\$@"' in macos
    # The previous macOS install left a symlink at $BIN_DIR/cast; writing over it
    # would go THROUGH the link and overwrite the package's console script.
    assert 'rm -f "$BIN_DIR/cast"' in macos
    # Reinstalls are idempotent: identical wrapper is reported, not rewritten.
    assert 'cmp -s "$tmp" "$BIN_DIR/cast"' in macos
    assert 'skip "$BIN_DIR/cast" "$BIN_DIR/cast"' in macos


def test_macos_sudoers_rule_is_named_single_path_verified_and_announced() -> None:
    """The rule is a passwordless root grant on one binary, so it must be: named for
    the sudo invoker (never %admin or ALL), restricted to one command path, checked
    by visudo BEFORE it lands (a broken file in /etc/sudoers.d breaks sudo for the
    whole machine), and announced out loud in both languages with the rule's path
    and its grantee. A silent grant is worse than the defect it fixes."""
    body = _body("setup_cast_sudoers")

    assert '[ "${OS_FAMILY:-linux}" = macos ] || return 0' in body
    assert 'rule="$SUDO_USER ALL=(root) NOPASSWD: $BIN_DIR/cast"' in body
    assert "%admin" not in body
    assert "NOPASSWD: ALL" not in body and "ALL=(ALL)" not in body
    # visudo gates the install, and a refused rule is never written.
    assert '"$VISUDO" -cf "$tmp"' in body
    assert body.index('"$VISUDO" -cf "$tmp"') < body.index('install -m 0440 "$tmp" "$rule_file"')
    assert "did not pass visudo - it was NOT installed" in body
    assert "не прошло visudo - оно НЕ установлено" in body
    # Reinstalls do not pile up duplicates: an identical rule is reported, not rewritten.
    assert '[ "$(cat "$rule_file")" = "$rule" ]' in body
    assert 'skip "$rule_file" "$rule_file"' in body
    # The grant is said out loud, naming both the grantee and the rule's path.
    assert "loud" in body
    assert "$SUDO_USER is granted passwordless sudo for the single command $BIN_DIR/cast" in body
    assert "$SUDO_USER выдан беспарольный sudo ровно на одну команду $BIN_DIR/cast" in body
    assert "(rule $rule_file)" in body and "(правило $rule_file)" in body
    # No invoker (root ran the installer directly): no unnamed rule may appear.
    assert '[ -z "${SUDO_USER:-}" ]' in body


def _cast_install_fns() -> str:
    """Both installer functions, cut out of install.sh the way the gate's other
    behaviour probes do it: the measure runs the real code, not a text double."""
    snippet = (
        "sed -n '/^install_cast_command()/,/^}/p;/^setup_cast_sudoers()/,/^}/p' "
        + shlex.quote(str(SCRIPT_PATH))
    )
    done = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True, check=True)
    return done.stdout


def _sandbox(box: Path, *, visudo_rc: int = 0) -> dict[str, str]:
    """A macOS-shaped sandbox: stub visudo recording its calls, BIN_DIR/PREFIX/SUDOERS_D
    under a tmp dir, OS_FAMILY forced so the macOS branch runs on any host."""
    sbin = box / "sbin"
    sbin.mkdir(parents=True)
    visudo = sbin / "visudo"
    visudo.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{box}/visudo.log"\nexit {visudo_rc}\n',
        encoding="utf-8",
    )
    visudo.chmod(0o755)
    return {
        "OS_FAMILY": "macos",
        "BIN_DIR": str(box / "bin"),
        "PREFIX": str(box),
        "SUDOERS_D": str(box / "sudoers.d"),
        "SUDO_USER": "tester",
        "VISUDO": str(visudo),
    }


_RUN_SNIPPET = """
set -u
{env}
{stubs}
{fns}
{calls}
"""


def _run_cast_install(
    box: Path, env: dict[str, str], *calls: str
) -> subprocess.CompletedProcess[str]:
    stubs = (
        "skip() { printf 'already in place: %s\\n' \"$1\"; }\n"
        "loud() { printf 'warning: %s\\n' \"$1\"; }\n"
        "die() { printf 'error: %s\\n' \"$1\" >&2; exit 1; }"
    )
    exports = "\n".join(f"{name}={shlex.quote(value)}" for name, value in env.items())
    snippet = _RUN_SNIPPET.format(
        env=exports, stubs=stubs, fns=_cast_install_fns(), calls="\n".join(calls)
    )
    return subprocess.run(["bash", "-c", snippet], capture_output=True, text=True, check=False)


@pytest.mark.machine
def test_the_wrapper_and_the_rule_land_once_and_survive_a_reinstall(tmp_path: Path) -> None:
    """Behaviour, not text: a stale symlink at $BIN_DIR/cast is REPLACED by the wrapper
    (not overwritten through the link), the named rule lands with mode 0440, and a
    second run reports both as already in place without rewriting or re-validating."""
    box = tmp_path / "box"
    (box / "venv" / "bin").mkdir(parents=True)
    (box / "venv" / "bin" / "cast").write_text("#!/bin/sh\n", encoding="utf-8")
    bin_dir = box / "bin"
    bin_dir.mkdir()
    (bin_dir / "cast").symlink_to(box / "venv" / "bin" / "cast")  # what a previous install left
    env = _sandbox(box)

    first = _run_cast_install(box, env, "install_cast_command", "setup_cast_sudoers")

    shown = first.stdout + first.stderr
    assert first.returncode == 0, shown
    wrapper = bin_dir / "cast"
    assert not wrapper.is_symlink(), "the wrapper was written THROUGH the stale symlink"
    assert (box / "venv" / "bin" / "cast").read_text(encoding="utf-8") == "#!/bin/sh\n"
    text = wrapper.read_text(encoding="utf-8")
    assert f'exec /usr/bin/sudo -n {bin_dir}/cast "$@"' in text
    assert 'PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"' in text
    rule = box / "sudoers.d" / "torrcast"
    rule_text = rule.read_text(encoding="utf-8")
    assert rule_text == f"tester ALL=(root) NOPASSWD: {bin_dir}/cast\n"
    assert oct(rule.stat().st_mode & 0o777) == "0o440"
    assert "passwordless sudo" in first.stdout, f"the grant was not announced: {shown!r}"

    second = _run_cast_install(box, env, "install_cast_command", "setup_cast_sudoers")

    shown = second.stdout + second.stderr
    assert second.returncode == 0, shown
    assert shown.count("already in place:") == 2, f"reinstall rewrote what was in place: {shown!r}"
    visudo_calls = (box / "visudo.log").read_text(encoding="utf-8").splitlines()
    assert len(visudo_calls) == 1, f"an identical rule was validated again: {visudo_calls!r}"
    assert rule.read_text(encoding="utf-8").count("NOPASSWD") == 1


@pytest.mark.machine
def test_a_rule_refused_by_visudo_is_never_installed(tmp_path: Path) -> None:
    """A broken file in /etc/sudoers.d breaks sudo on the owner's whole laptop:
    the installer's answer to a visudo refusal is a failure, not a written file."""
    box = tmp_path / "box"
    box.mkdir()
    done = _run_cast_install(box, _sandbox(box, visudo_rc=1), "setup_cast_sudoers")

    shown = done.stdout + done.stderr
    assert done.returncode != 0, f"a visudo refusal was swallowed: {shown!r}"
    assert "did not pass visudo" in shown
    assert not (box / "sudoers.d" / "torrcast").exists()


@pytest.mark.machine
def test_an_invokerless_install_writes_no_unnamed_rule(tmp_path: Path) -> None:
    """Root ran the installer directly: there is no one to name, and an unnamed or
    group-wide rule would be a silent grant - refuse it out loud instead."""
    box = tmp_path / "box"
    box.mkdir()
    env = _sandbox(box)
    env["SUDO_USER"] = ""
    done = _run_cast_install(box, env, "setup_cast_sudoers")

    shown = done.stdout + done.stderr
    assert done.returncode == 0, shown
    assert "no sudo invoker is known" in shown
    assert not (box / "sudoers.d" / "torrcast").exists()


@pytest.mark.skipif(
    sys.platform != "darwin", reason="the wrapper and its rule exist only on an installed Mac"
)
def test_the_installed_cast_is_the_root_rexec_wrapper_on_macos() -> None:
    """Refuse on Linux: a text double cannot prove what /usr/local/bin/cast IS on the
    Mac. There the entry point must be a regular file (not the old symlink) whose
    sudoers rule passes visudo."""
    cast = Path("/usr/local/bin/cast")
    assert cast.is_file() and not cast.is_symlink()
    assert "sudo -n" in cast.read_text(encoding="utf-8")
    done = subprocess.run(
        ["visudo", "-cf", "/etc/sudoers.d/torrcast"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr


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
