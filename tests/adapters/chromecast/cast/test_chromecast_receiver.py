"""Приёмник целиком: договор порта, слои под ним и пультовые команды без сторожа."""

from __future__ import annotations

import importlib
import inspect

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
    assert ChromecastReceiver.CUT_SLACK == _Settings.CUT_SLACK


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


#: Занятие показа и файл, в котором оно живёт: имя метода приёмника - имя занятия.
_TASKS = (
    ("play", "play"),
    ("stop", "stop"),
    ("position", "position"),
    ("replay", "replay"),
    ("_say_skip", "say_skip"),
    ("_past_deadly", "past_deadly"),
    ("_reload", "reload"),
    ("_nudge", "nudge"),
    ("_watch_seek", "watch_seek"),
    ("_drop_seek", "drop_seek"),
)


@pytest.mark.parametrize(("method", "file"), _TASKS)
def test_every_task_of_the_show_is_forwarded_to_its_own_file(method: str, file: str) -> None:
    """Метод приёмника - имя занятия, а тело занятия лежит своим файлом рядом.

    Спрашивается тут именно связь: метод обязан звать СВОЁ занятие и ничьё чужое, и
    занятие это обязано быть тем самым, что лежит в одноимённом файле. Разъедься имя
    метода и занятие - показ звал бы чужую работу молча, и это была бы ровно та
    поломка, которую в файле на девятьсот строк не видно.
    """
    unit = f"_{file}"
    called = ChromecastReceiver.__dict__[method].__code__.co_names

    assert called == (unit,), f"{method} зовёт {called}, а обязан звать одно занятие {unit}"
    home_of_unit = importlib.import_module(f"torrcast.adapters.chromecast.cast.{file}")
    assert getattr(home, unit) is getattr(home_of_unit, unit), "занятие взято не из своего файла"


@pytest.mark.parametrize(("method", "file"), _TASKS)
def test_the_task_is_asked_for_exactly_what_the_method_promised(method: str, file: str) -> None:
    """Договор метода и договор занятия - один: приёмник добавляет к нему только себя.

    Разойдись они - подмена аргументов проехала бы молча: занятие взяло бы место
    вторым числом там, где метод обещал первое, и разница видна была бы только на
    экране. Проверяется тут ровно то, чего не видит сверка имён.
    """
    unit = getattr(home, f"_{file}")
    promised = list(inspect.signature(ChromecastReceiver.__dict__[method]).parameters.values())
    asked = list(inspect.signature(unit).parameters.values())

    assert promised[0].name == "self" and asked[0].name in {"rcv", "receiver"}
    assert promised[1:] == asked[1:], "занятие спрашивает не то, что метод обещал"
