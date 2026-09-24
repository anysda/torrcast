"""A new sender must not inherit a dead sender's receiver application."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from tests.adapters.chromecast.cast.wired import Controller, Device, Wired
from tests.fakes.clock import FakeClock
from torrcast.domain.infra_error import InfraError
from web.tv_load import tv_load
from web.tv_session import TvSession

URL = "http://media.example:8080/index.m3u8"


class _Previous(Device):
    def __init__(self, state: str = "PLAYING", app: str = "CC1AD845", url: str = URL):
        super().__init__(app=app, session="previous-process")
        self.media_controller.status.player_state = state
        self.media_controller.status.content_id = url


class _NewSender(Wired):
    def _load(self, at: float = 0.0, paused: bool = False) -> None:
        self.device.said.append("load")
        self._session = "new-process"

    def _settle(self, budget: float) -> bool:
        return True


@pytest.mark.parametrize("state", ["PLAYING", "PAUSED", "IDLE"])
@pytest.mark.parametrize("entry", ["web", "cli"])
def test_new_sender_closes_its_previous_application_before_loading(state: str, entry: str) -> None:
    device = _Previous(state)
    receiver = _NewSender(device=device, clock=FakeClock())

    session = TvSession(factory=lambda address, profile: receiver)
    try:
        if entry == "web":
            session.start("receiver.example", "New show", URL, 42.0)
        else:
            receiver.play(URL, "New show", at=42.0)
        assert device.said == ["quit_app", "disconnect", "load"]
    finally:
        session.stop()


@pytest.mark.parametrize(
    ("app", "url"),
    [
        ("YouTube", URL),
        ("CC1AD845", "http://another.example:8080/index.m3u8"),
        ("CC1AD845", "http://media.example:8081/index.m3u8"),
        ("CC1AD845", "http://media.example:8080/other/index.m3u8"),
        ("CC1AD845", ""),
        ("", URL),
    ],
)
def test_recovery_does_not_close_an_unidentified_or_foreign_cast(app: str, url: str) -> None:
    device = _Previous(app=app, url=url)
    receiver = _NewSender(device=device, clock=FakeClock())

    receiver.play(URL)

    assert device.said == ["load"]


def test_the_next_episode_of_the_same_sender_keeps_its_application() -> None:
    device = _Previous()
    receiver = _NewSender(device=device, clock=FakeClock())
    receiver._session = device.status.session_id

    receiver.play(URL)

    assert device.said == ["load"]


class _Reply(Controller):
    def __init__(self, device: Device, url: str, *, fail: bool = False, changed: bool = False):
        super().__init__()
        self.device, self.url = device, url
        self.fail, self.changed = fail, changed
        self.status.content_id = URL

    def update_status(
        self, *, callback_function: Callable[[bool, dict[str, Any] | None], None] | None = None
    ) -> None:
        self.status.content_id = self.url
        if self.changed:
            self.device.status.session_id = "another-sender"
        assert callback_function is not None
        callback_function(not self.fail, {})


@pytest.mark.parametrize("changed", [False, True])
def test_ownership_uses_the_completed_reply_and_the_same_application_session(changed: bool) -> None:
    device = _Previous()
    url = URL if changed else "http://another.example/index.m3u8"
    device.media_controller = _Reply(device, url, changed=changed)
    receiver = _NewSender(device=device, clock=FakeClock())

    receiver.play(URL)

    assert device.said == ["load"]


def test_failed_status_disconnects_without_closing_an_unclaimed_application() -> None:
    device = _Previous()
    device.media_controller = _Reply(device, URL, fail=True)
    receiver = _NewSender(device=device, clock=FakeClock())

    with pytest.raises(InfraError, match="did not accept the cast"):
        tv_load(receiver, URL, "New show", 42.0, None)

    assert device.said == ["disconnect"]
    assert receiver._cast is None


def test_initially_empty_media_cache_is_filled_before_ownership_is_checked() -> None:
    device = _Previous()
    device.media_controller = _Reply(device, URL)
    device.media_controller.status.content_id = ""
    receiver = _NewSender(device=device, clock=FakeClock())

    receiver.play(URL)

    assert device.said == ["quit_app", "disconnect", "load"]
