"""Telegram получает слова CLI-отказа, а не его голый код."""

import sys
from typing import cast

from tests.test_bot import _Api
from tgbot.bot import Bot
from tgbot.config import Config
from tgbot.telegram_api import TelegramApi
from torrcast.usecases.choice.configure import _environment_port, configure


def test_nonzero_command_sends_its_spoken_reason() -> None:
    api = _Api()
    previous = _environment_port()

    def command(_args: object) -> int:
        print("телевизор не ответил за 350 с", file=sys.stderr)
        return 2

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
                "message": {
                    "chat": {"id": -100},
                    "message_id": 9,
                    "text": "cast мумия",
                }
            }
        )
        bot.run_one()
    finally:
        configure(previous)

    assert api.sent == ["The cast did not start: телевизор не ответил за 350 с"]
