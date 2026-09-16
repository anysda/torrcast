"""Сборка пульта показа с обложкой: одно место на весь бот."""

from __future__ import annotations

from tgbot.playing_poster import PlayingPoster
from tgbot.telegram_api import TelegramApi
from tgbot.telegram_control import TelegramControl


def dressed_control(api: TelegramApi, chat_id: str, *, remember: bool) -> TelegramControl:
    """Пульт, одетый в обложку играющего; её нет - пульт остаётся текстовым."""
    return TelegramControl(api, chat_id, remember=remember, poster=PlayingPoster())
