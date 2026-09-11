"""Проверяет настоящий приёмник «На ТВ» и шаг его опроса (:mod:`web.live_receiver`)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver
from torrcast.domain.profile import CAUTIOUS
from web.live_receiver import POLL_SECONDS, live_receiver


@pytest.mark.machine
def test_the_page_does_not_pull_pychromecast_until_someone_casts() -> None:
    """Страница поднимается без pychromecast: он нужен только в миг «На ТВ»."""
    probe = "import sys, web.live_receiver; print('pychromecast' in sys.modules)"
    said = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout.strip()

    assert said == "False"


def test_the_live_receiver_is_the_chromecast_with_the_given_profile() -> None:
    made = live_receiver("192.168.1.90", CAUTIOUS)

    assert isinstance(made, ChromecastReceiver)
    assert made.address == "192.168.1.90"
    assert made.profile is CAUTIOUS
    assert POLL_SECONDS == 2.0
