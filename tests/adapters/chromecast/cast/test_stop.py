"""Снятие каста: чужой показ неприкосновенен, а своё приложение закрывается до конца."""

from __future__ import annotations

from tests.adapters.chromecast.cast.wired import Device, Wired
from torrcast.adapters.chromecast.cast.stop import _stop


def test_the_show_is_taken_down_but_the_app_is_left_for_the_next_episode() -> None:
    """Между сериями приложение не закрывается: оно достанется следующей."""
    receiver = Wired()
    receiver._session = "наша"

    _stop(receiver)

    assert receiver.device.media_controller.said == ["stop"]
    assert receiver.device.said == []
    assert receiver._cast is not None


def test_quitting_the_app_also_drops_our_own_connection() -> None:
    """Сендер, переживший своё приложение, для следующего показа - «второй pychromecast».

    Из-за него приёмник и отдаёт пустой MEDIA_STATUS при идущей на экране картинке.
    """
    receiver = Wired()
    receiver._session = "наша"

    _stop(receiver, quit_app=True)

    assert receiver.device.said == ["quit_app", "disconnect"]
    assert receiver._cast is None
    assert receiver._session == ""


def test_a_foreign_show_is_not_touched_at_all() -> None:
    """На том же ТВ живут другие сендеры, и кастят они через тот же Default Media Receiver."""
    receiver = Wired(device=Device(app="чужое"))

    _stop(receiver, quit_app=True)

    assert receiver.device.media_controller.said == []
    assert receiver.device.said == []


def test_a_receiver_that_was_never_connected_has_nothing_to_take_down() -> None:
    """Соединение не поднимали - и снимать нечего: будить ТВ ради этого незачем."""
    receiver = Wired()
    receiver._cast = None

    _stop(receiver, quit_app=True)

    assert receiver.device.said == []
