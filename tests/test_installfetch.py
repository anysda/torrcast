"""Постоянный HTTP-отказ отпускает загрузчик к запасному источнику без пауз."""

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]


@pytest.mark.machine
@pytest.mark.parametrize(("failure", "calls"), [(22, 1), (35, 2)])
def test_fetch_retries_transport_but_releases_http_failure(
    tmp_path: Path, failure: int, calls: int
) -> None:
    """Целый установщик загружен: тот же fetch, который читает архивы и JSON."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    called = tmp_path / "called"
    (bindir / "curl").write_text(
        "#!/bin/sh\n"
        f'echo call >> "{called}"\n'
        f'[ "$(wc -l < "{called}")" -gt 1 ] || exit {failure}\n'
        "printf '{\"downloaded\":true}'\n",
        encoding="utf-8",
    )
    (bindir / "curl").chmod(0o755)
    # Считаем сами бесполезные попытки, а не ждём их паузы в отрицательной пробе.
    (bindir / "sleep").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (bindir / "sleep").chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "TORRCAST_NO_ROOT": "1",
        "TORRCAST_NO_SYSTEMD": "1",
        "TORRCAST_PLAIN": "1",
        "TORRCAST_PHASES": "none",
        "TORRCAST_PREFIX": str(tmp_path / "prefix"),
        "TORRCAST_CONFIG_DIR": str(tmp_path / "cfg"),
        "TORRCAST_STATE_DIR": str(tmp_path / "state"),
        "TORRCAST_BIN_DIR": str(bindir),
        "TORRCAST_LANGUAGE": "en",
        "TORRCAST_DL_TRIES": "4",
    }
    script = 'p="$1"; set --; . "$p" >/dev/null; fetch https://example.invalid/archive'
    done = subprocess.run(
        ["bash", "-c", script, "_", str(REPO / "install.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert len(called.read_text().splitlines()) == calls, done.stdout + done.stderr
    if failure == 22:
        assert done.returncode == 22, done.stdout + done.stderr
        assert "retrying" not in done.stderr
    else:
        assert done.returncode == 0, done.stdout + done.stderr
        assert done.stdout == '{"downloaded":true}'
        assert "retrying" in done.stderr
