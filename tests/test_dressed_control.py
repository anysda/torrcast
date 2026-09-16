"""Сборка пульта показа с обложкой."""

from typing import cast

from tests.test_telegram_menu import _Api
from tgbot.dressed_control import dressed_control
from tgbot.playing_poster import PlayingPoster
from tgbot.telegram_api import TelegramApi


def test_the_remote_of_the_bot_is_built_with_the_playing_cover() -> None:
    """Бот собирает пульт с добытчиком обложки, а не голым текстовым."""
    control = dressed_control(cast(TelegramApi, _Api()), "-100", remember=False)

    assert isinstance(control._poster, PlayingPoster)
