"""Транскрипты живых команд, пришедших занятому Telegram-боту."""

from __future__ import annotations

import sys
import threading
import time
from typing import cast

import pytest

from tests.fakes.journal import Tape
from tgbot.bot import Bot
from tgbot.config import Config
from tgbot.telegram_api import TelegramApi
from tgbot.transport import _TelegramResult
from torrcast.domain.exit_codes import EXIT_NOT_FOUND
from torrcast.ports.abandon import slot as abandon_slot
from torrcast.ports.journal.slot import install as install_journal


class _Api:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.answers: list[str] = []

    def send(self, _chat: str, text: str, _buttons: object = None, **_kw: object) -> int:
        self.sent.append(text)
        return len(self.sent)

    def post(
        self, _chat: str, text: str, _buttons: object = None, **_kw: object
    ) -> _TelegramResult:
        self.sent.append(text)
        return _TelegramResult(200, "", {"message_id": len(self.sent)})

    def answer(self, _callback: str, text: str = "") -> object:
        self.answers.append(text)
        return object()

    def delete(self, _chat: str, _message: int) -> object:
        return object()

    def edit(self, _chat: str, _message: int, _text: str, _buttons: object = None) -> object:
        return object()


def _message(number: int, text: str) -> dict[str, object]:
    return {"message": {"chat": {"id": -100}, "message_id": number, "text": text}}


@pytest.mark.machine
def test_a_live_cast_replaces_the_show_that_is_still_raising(
    _russian_product: None, _ports_restored: None
) -> None:
    api, tape = _Api(), Tape()
    install_journal(tape)
    began = threading.Event()
    taken: list[list[str]] = []

    def command(argv: object) -> int:
        args = list(cast(list[str], argv))
        taken.append(args)
        if len(taken) == 1:
            began.set()
            deadline = time.monotonic() + 2.0
            while not abandon_slot.abandoned() and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            assert abandon_slot.abandoned()
        return 0

    bot = Bot(
        Config("token", "-100"),
        api=cast(TelegramApi, api),
        command=command,
        assemble=lambda: None,
        title=lambda: "Муха (1986)" if taken == [["матрица"], ["муха"]] else "",
        stop=lambda: None,
    )
    bot.dispatch(_message(1, "cast матрица"))
    running = threading.Thread(target=bot.run_one)
    running.start()
    assert began.wait(2.0)
    bot.dispatch(_message(2, "cast муха"))
    running.join(2.0)
    assert not running.is_alive()
    bot.run_one()

    assert taken == [["матрица"], ["муха"]]
    assert api.sent == ["Предыдущий запрос остановлен. Запускаю новый.", "Муха (1986)"]
    assert tape.named("telegram/incoming") == [
        {"command": "cast матрица"},
        {"command": "cast муха"},
    ]
    assert tape.named("telegram/replaced") == [{"command": "cast муха", "occupied": "cast матрица"}]


def test_two_commands_before_execution_leave_only_the_last_one(
    _russian_product: None, _ports_restored: None
) -> None:
    api = _Api()
    taken: list[list[str]] = []

    def command(argv: object) -> int:
        taken.append(list(cast(list[str], argv)))
        return 0

    bot = Bot(
        Config("token", "-100"),
        api=cast(TelegramApi, api),
        command=command,
        assemble=lambda: None,
        title=lambda: "",
    )

    bot.dispatch(_message(1, "cast первый"))
    bot.dispatch(_message(2, "cast последний"))
    bot.run_one()

    assert taken == [["последний"]]
    assert api.sent == ["Предыдущий запрос остановлен. Запускаю новый."]


def test_an_impossible_auto_episode_refuses_at_once_and_leaves_the_next_command_free(
    _russian_product: None, _ports_restored: None
) -> None:
    api, tape = _Api(), Tape()
    install_journal(tape)
    detail = (
        "серии s3e24 в этой раздаче нет (сезоны 1-8 · серий 157: s1e1...s8e23)"
        " - возьми другую раздачу: cast <запрос> --release N"
    )
    taken: list[list[str]] = []

    def command(argv: object) -> int:
        args = list(cast(list[str], argv))
        taken.append(args)
        if args[-1:] == ["s3e24"]:
            print(detail, file=sys.stderr)
            return EXIT_NOT_FOUND
        return 0

    bot = Bot(
        Config("token", "-100"),
        api=cast(TelegramApi, api),
        command=command,
        assemble=lambda: None,
        title=lambda: "Матрица (1999)" if taken[-1:] == [["матрица"]] else "",
    )
    bot.dispatch(_message(1, "cast домохозяйки s3e24"))
    bot.run_one()
    bot.dispatch(_message(2, "cast матрица"))
    bot.run_one()

    assert api.sent == [f"Каст не начался: {detail}", "Матрица (1999)"]
    assert tape.named("telegram/refused") == [
        {
            "command": "cast домохозяйки s3e24",
            "occupied": "cast домохозяйки s3e24",
            "detail": detail,
        }
    ]


def test_a_button_from_an_old_menu_refuses_and_names_the_live_command_in_the_trace(
    _russian_product: None, _ports_restored: None
) -> None:
    api, tape = _Api(), Tape()
    install_journal(tape)
    bot = Bot(
        Config("token", "-100"),
        api=cast(TelegramApi, api),
        command=lambda _argv: 0,
        assemble=lambda: None,
        title=lambda: "",
    )
    bot.dispatch(_message(1, "cast новый фильм"))
    bot.dispatch(
        {
            "callback_query": {
                "id": "old",
                "data": "pick:old:2",
                "message": {"message_id": 90, "chat": {"id": -100}},
            }
        }
    )

    assert api.answers == ["Это меню картин уже не действует."]
    assert tape.named("telegram/refused") == [
        {"command": "button", "occupied": "cast новый фильм", "detail": ""}
    ]
