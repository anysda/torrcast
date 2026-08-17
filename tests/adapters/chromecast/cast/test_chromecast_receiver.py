"""Приёмник целиком: договор порта, слои под ним и пультовые команды без сторожа."""

from __future__ import annotations

import pytest

from tests.adapters.chromecast.cast.wired import Wired
from torrcast.adapters.chromecast.cast import chromecast_receiver as home
from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver
from torrcast.adapters.chromecast.cast.receiver_settings import _Settings
from torrcast.adapters.chromecast.cast.receiver_state import _State
from torrcast.adapters.chromecast.cast.receiver_talk import _Talk
from torrcast.ports.receiver import Receiver


def test_the_receiver_answers_the_whole_contract_the_layers_are_given() -> None:
    """Слои знают только договор порта - приёмник обязан отвечать на него целиком."""
    receiver: Receiver = Wired()

    for name in ("play", "stop", "position", "replay", "seek", "pause", "resume"):
        assert callable(getattr(receiver, name)), f"порт спрашивает {name}, а его нет"


def test_the_layers_under_the_receiver_stand_in_the_order_they_depend_on_each_other() -> None:
    """Пороги под полями, поля под разговором, разговор под показом.

    Перепутай порядок - и занятие показа звало бы ручку, которой на его слое ещё нет.
    """
    assert issubclass(ChromecastReceiver, _Talk)
    assert issubclass(_Talk, _State)
    assert issubclass(_State, _Settings)


def test_the_thresholds_are_reachable_from_the_receiver_itself() -> None:
    """Их спрашивают снаружи - показ, щупы и тесты, - поэтому они и остались атрибутами."""
    assert ChromecastReceiver.DEADLY_TRIES == _Settings.DEADLY_TRIES
    assert ChromecastReceiver.PICTURE_STEP == _Settings.PICTURE_STEP
    assert ChromecastReceiver.STALL_SKIP == _Settings.STALL_SKIP


def test_the_remote_commands_do_not_touch_the_watchdog_state() -> None:
    """Перемотка проверяется ВМЕСТЕ со сторожем: подчищать его вход значило бы проверять не то.

    Существует она ради диагностики: автотест кнопку нажать не может, а вторым
    pychromecast её не подать вовсе - приёмник считает второе соединение тем же сендером.
    """
    receiver = Wired()
    receiver._peak, receiver._stall_hits = 500.0, 2

    receiver.seek(900.0)
    receiver.pause()
    receiver.resume()

    assert receiver.device.media_controller.jumps == [900.0]
    assert receiver.device.media_controller.said == ["pause", "play"]
    assert (receiver._peak, receiver._stall_hits) == (500.0, 2)


def test_every_task_of_the_show_is_forwarded_to_its_own_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Метод приёмника - имя занятия, а тело занятия лежит своим файлом рядом.

    Проверяется именно передача: разъедься имя метода и занятие, показ звал бы чужую
    работу молча - и это была бы ровно та поломка, которую в файле на девятьсот строк
    не видно.
    """
    receiver = Wired()
    calls: list[tuple[str, tuple[object, ...]]] = []

    for name in ("_play", "_stop", "_position", "_replay", "_say_skip", "_nudge"):

        def spy(_rcv: object, *rest: object, _name: str = name) -> None:
            calls.append((_name, rest))

        monkeypatch.setattr(home, name, spy)

    receiver.play("http://дом/поток.m3u8", "Моана", 10.0)
    receiver.stop(quit_app=True)
    receiver.position(front=144.0)
    receiver.replay(500.0)
    receiver._say_skip(200.0)
    receiver._nudge(84.0, 144.0)

    assert calls == [
        ("_play", ("http://дом/поток.m3u8", "Моана", 10.0)),
        ("_stop", (True,)),
        ("_position", (144.0,)),
        ("_replay", (500.0,)),
        ("_say_skip", (200.0,)),
        ("_nudge", (84.0, 144.0)),
    ]
