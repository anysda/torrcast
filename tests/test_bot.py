"""Зеркало развилки обновлений Telegram-бота."""

from __future__ import annotations

from typing import cast

from tgbot.bot import Bot
from tgbot.config import Config
from tgbot.telegram_api import TelegramApi
from torrcast.usecases.choice.configure import _environment_port, configure


class _Api:
    """Записывает сообщения и ответы callback без сети."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.deleted: list[int] = []

    def send(
        self,
        _chat_id: str,
        text: str,
        _buttons: object = None,
        reply_to_message_id: int | None = None,
    ) -> int:
        del reply_to_message_id
        self.sent.append(text)
        return 1

    def delete(self, _chat_id: str, message_id: int) -> object:
        self.deleted.append(message_id)
        return object()

    def answer(self, _callback_id: str, _text: str = "") -> object:
        return object()

    def edit(self, _chat_id: str, _message_id: int, _text: str, _buttons: object = None) -> object:
        return object()


def test_plain_cast_command_runs_without_forcing_terminal_menu_flag() -> None:
    api = _Api()
    assert callable(api.send)
    commands: list[list[str]] = []
    previous = _environment_port()

    def command(argv: object) -> int:
        commands.append(list(cast(list[str], argv)))
        return 0

    try:
        bot = Bot(
            Config("token", "-100"),
            api=cast(TelegramApi, api),
            command=command,
            assemble=lambda: None,
            title=lambda: "Мумия (2026)",
        )
        bot.dispatch(
            {
                "message": {
                    "chat": {"id": -100},
                    "from": {"language_code": "ru"},
                    "message_id": 9,
                    "text": "cast мумия",
                }
            }
        )
        bot.run_one()
    finally:
        configure(previous)

    assert commands == [["мумия"]]
    assert api.sent == ["Мумия (2026)"]


def test_chat_menu_flag_reaches_the_cli_unchanged() -> None:
    """Настоящий CLI остаётся в главном потоке и вправе ставить сигналы."""
    api = _Api()
    previous = _environment_port()

    try:
        commands: list[list[str]] = []

        def command(argv: object) -> int:
            commands.append(list(cast(list[str], argv)))
            return 0

        bot = Bot(
            Config("token", "-100"),
            api=cast(TelegramApi, api),
            command=command,
            assemble=lambda: None,
            title=lambda: "Мумия (2026)",
        )
        bot.dispatch(
            {
                "message": {
                    "chat": {"id": -100},
                    "from": {"language_code": "ru"},
                    "message_id": 8,
                    "text": "cast мумия --menu",
                }
            }
        )
        bot.run_one()
    finally:
        configure(previous)

    assert commands == [["мумия", "--menu"]]


def test_stop_button_runs_only_the_cast_stop_command() -> None:
    api = _Api()
    commands: list[list[str]] = []
    previous = _environment_port()

    def command(argv: object) -> int:
        commands.append(list(cast(list[str], argv)))
        return 0

    try:
        bot = Bot(
            Config("token", "-100"),
            api=cast(TelegramApi, api),
            command=command,
            assemble=lambda: None,
            title=lambda: "",
        )
        bot.dispatch(
            {
                "callback_query": {
                    "id": "cb",
                    "data": "control:stop",
                    "chat_instance": "x",
                    "from": {"language_code": "ru"},
                    "message": {"message_id": 7, "chat": {"id": -100}},
                }
            }
        )
        bot.run_one()
    finally:
        configure(previous)

    assert commands == [["stop"]]
    assert api.sent == []


def test_stop_cleans_the_whole_cast_chat_even_when_command_deletion_is_refused() -> None:
    class Api(_Api):
        def __init__(self) -> None:
            super().__init__()
            self.next_id = 20

        def send(
            self,
            _chat_id: str,
            text: str,
            _buttons: object = None,
            reply_to_message_id: int | None = None,
        ) -> int:
            del reply_to_message_id
            self.sent.append(text)
            self.next_id += 1
            return self.next_id

        def delete(self, _chat_id: str, message_id: int) -> object:
            self.deleted.append(message_id)
            if message_id == 9:
                raise RuntimeError("message can't be deleted")
            return object()

    api = Api()
    commands: list[list[str]] = []
    previous = _environment_port()

    def command(argv: object) -> int:
        args = list(cast(list[str], argv))
        commands.append(args)
        if args != ["stop"]:
            environment = _environment_port()
            environment.write("беру Мумия; список: cast мумия --menu")
            environment.menu().show(["1. Мумия (1999)", "2. Мумия (2026)"])
        return 0

    try:
        bot = Bot(
            Config("token", "-100"),
            api=cast(TelegramApi, api),
            command=command,
            assemble=lambda: None,
            title=lambda: "Мумия (2026)",
        )
        bot.dispatch(
            {
                "message": {
                    "message_id": 9,
                    "chat": {"id": -100},
                    "from": {"language_code": "ru"},
                    "text": "cast мумия",
                }
            }
        )
        bot.run_one()
        bot.dispatch(
            {
                "callback_query": {
                    "id": "cb",
                    "data": "control:stop",
                    "from": {"language_code": "ru"},
                    "message": {"message_id": 23, "chat": {"id": -100}},
                }
            }
        )
        bot.run_one()
    finally:
        configure(previous)

    assert commands == [["мумия"], ["stop"]]
    assert set(api.deleted) == {9, 21, 22, 23}
