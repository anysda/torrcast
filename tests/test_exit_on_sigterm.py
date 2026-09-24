"""Зеркало :func:`tgbot.exit_on_sigterm.exit_on_sigterm`."""

from __future__ import annotations

import signal
import subprocess
import sys

import pytest


@pytest.mark.machine
def test_sigterm_exits_the_idle_service_cleanly() -> None:
    """В простое служба заканчивается нулём, а не возвращается в вечное ожидание."""
    script = """
import signal
from tgbot.exit_on_sigterm import exit_on_sigterm

exit_on_sigterm()
print("ready", flush=True)
signal.pause()
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", script], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "ready"
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=5.0)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    assert proc.returncode == 0
    assert out == ""
    assert err == ""
