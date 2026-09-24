"""SIGTERM моста во время поручения: снять показ и закончить вечный цикл."""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time

import pytest


@pytest.mark.machine
def test_sigterm_during_a_show_stops_it_and_exits_within_five_seconds() -> None:
    """Сигнал не становится концом одной команды: за ним уходят показ и сам мост."""
    script = r"""
import json
import signal
import time
from collections.abc import Sequence

from hass.bridge import Bridge
from hass.stopping import STOP
from tests.fakes.playback_session import FakePlaybackSession
from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver
from torrcast.cli.answered import answered


class Session(FakePlaybackSession):
    def __init__(self):
        super().__init__(receiver="mock")
        self.receiver = MockReceiver()

    def stop(self):
        super().stop()
        self.receiver.stop()
        self.playing = False


session = Session()


def command(argv: Sequence[str] | None) -> int:
    if list(argv or []) == [STOP]:
        return 0

    def show() -> int:
        session.playing = True
        print("show started: mock receiver, warm-up running", flush=True)
        while True:
            time.sleep(1)

    return answered(show)


bridge = Bridge(session=session, command=command)
bridge.play("матрица")
signal.signal(signal.SIGTERM, lambda _number, _frame: bridge.stop())
bridge.run()
print(json.dumps({"stopped": session.stopped, "playing": session.playing}), flush=True)
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", script], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "show started: mock receiver, warm-up running"
        began = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=5.0)
        elapsed = time.monotonic() - began
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    assert proc.returncode == 0
    assert elapsed <= 5.0
    assert json.loads(out) == {"stopped": 1, "playing": False}
    assert err == "command interrupted by SIGTERM\n"


@pytest.mark.machine
def test_bot_sigterm_leaves_a_command_and_the_service() -> None:
    """Тот же вложенный обработчик не возвращает бота в его вечный цикл."""
    script = r"""
import time

import tgbot.bot as bot_module
from torrcast.cli.answered import answered


class Service:
    def run(self):
        def command():
            print("bot command started", flush=True)
            while True:
                time.sleep(1)
        answered(command)
        while True:
            time.sleep(1)


bot_module.Config.load = lambda: object()
bot_module.Bot = lambda _config: Service()
bot_module._bot()
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", script], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "bot command started"
        began = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        _out, err = proc.communicate(timeout=5.0)
        elapsed = time.monotonic() - began
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    assert proc.returncode == 0
    assert elapsed <= 5.0
    assert err == "command interrupted by SIGTERM\n"
