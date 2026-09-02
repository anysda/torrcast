"""Зеркало громкости: молчащий приёмник отвечает ``null``, а не прошлым числом."""

from __future__ import annotations

from typing import Any

from hass.volume import Volume


class _Receiver:
    """Приёмник из памяти: сети тут нет ни одного байта."""

    def __init__(self, level: float | None = 0.3) -> None:
        self.status = type("_Status", (), {"volume_level": level})()
        self.wanted: list[float] = []
        self.disconnected = 0

    def set_volume(self, level: float) -> None:
        self.wanted.append(level)

    def disconnect(self) -> None:
        self.disconnected += 1


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_the_level_is_read_once_and_kept_fresh_for_a_while() -> None:
    device = _Receiver()
    clock = _Clock()
    opened: list[str] = []

    def connect(address: str) -> Any:
        opened.append(address)
        return device

    volume = Volume("10.0.1.7", connect=connect, fresh=10.0, clock=clock)

    assert volume.level() == 0.3
    clock.now = 5.0
    assert volume.level() == 0.3
    assert opened == ["10.0.1.7"]  # опрос раз в несколько секунд не воет на приёмник


def test_a_receiver_that_will_not_open_answers_null_and_not_a_stale_number() -> None:
    def refuse(_address: str) -> Any:
        raise OSError("приёмник не отозвался")

    volume = Volume("10.0.1.7", connect=refuse)

    assert volume.level() is None
    assert volume.set(0.5) is False


def test_an_unnamed_receiver_is_not_asked_at_all() -> None:
    asked: list[str] = []

    def connect(address: str) -> Any:
        asked.append(address)
        return _Receiver()

    volume = Volume("", connect=connect)

    assert volume.level() is None
    assert asked == []


def test_the_level_is_absolute_and_stays_inside_the_receiver_range() -> None:
    device = _Receiver()
    volume = Volume("10.0.1.7", connect=lambda _address: device)

    assert volume.set(0.42) is True
    assert volume.set(7.0) is True
    assert device.wanted == [0.42, 1.0]


def test_leaving_lets_the_receiver_go() -> None:
    device = _Receiver()
    volume = Volume("10.0.1.7", connect=lambda _address: device)
    volume.level()

    volume.close()

    assert device.disconnected == 1
