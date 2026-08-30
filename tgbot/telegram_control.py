"""Inline-пульт текущего показа через ручку владеющего процесса."""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path

from tgbot.telegram_api import TelegramApi
from torrcast.domain.debug_handles import CTL_ENV

VOL_STEP = 0.02


class TelegramControl:
    """Рисует пульт и кладёт одноразовые команды процессу показа."""

    def __init__(self, api: TelegramApi, chat_id: str, path: Path | None = None) -> None:
        self._api = api
        self._chat_id = chat_id
        self._path = path or Path(f"/tmp/torrcast-telegram-{os.getuid()}.ctl")
        self._message_id = 0
        os.environ[CTL_ENV] = str(self._path)

    @staticmethod
    def buttons() -> list[list[dict[str, str]]]:
        """Назвать кнопки без питания телевизора."""
        return [
            [
                {"text": "⏪", "callback_data": "control:seekby -30"},
                {"text": "⏯", "callback_data": "control:toggle"},
                {"text": "⏩", "callback_data": "control:seekby 30"},
            ],
            [
                {"text": "🔉", "callback_data": f"control:volume -{VOL_STEP}"},
                {"text": "⏹", "callback_data": "control:stop"},
                {"text": "🔊", "callback_data": f"control:volume {VOL_STEP}"},
            ],
        ]

    def show(self, text: str) -> int:
        """Показать пульт одним сообщением после запуска каста."""
        self._message_id = self._api.send(self._chat_id, text, self.buttons())
        return self._message_id

    def clean(self) -> None:
        """Убрать пульт, не связывая успех остановки с правами Telegram."""
        if self._message_id:
            with suppress(Exception):
                self._api.delete(self._chat_id, self._message_id)
            self._message_id = 0

    def command(self, data: str) -> str | None:
        """Записать команду показа; stop оставить команде приложения."""
        prefix = "control:"
        if not data.startswith(prefix):
            return None
        command = data.removeprefix(prefix)
        if command == "stop":
            return command
        if command == "toggle":
            command = "toggle"
        allowed = ("seekby ", "volume ")
        if command != "toggle" and not command.startswith(allowed):
            return None
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(command, encoding="utf-8")
        temporary.replace(self._path)
        return command
