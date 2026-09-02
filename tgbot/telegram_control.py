"""Inline-пульт текущего показа через ручку владеющего процесса."""

from __future__ import annotations

import os
import threading
from contextlib import suppress
from pathlib import Path

from tgbot.telegram_api import TelegramApi
from tgbot.transport import _TelegramResult
from torrcast.domain.debug_handles import CTL_ENV

VOL_STEP = 0.02


class _TelegramError(Exception):
    """Отказ Bot API пульту показа: названы статус и подробность, токена в строке нет."""


def _refused(result: _TelegramResult) -> _TelegramError:
    """Назвать отказ раздельно: беда сети (статус 0) пройдёт сама, 401 - нет."""
    if result.status == 0:
        return _TelegramError(f"network: {result.detail}")
    return _TelegramError(f"HTTP {result.status}: {result.detail}")


class TelegramControl:
    """Рисует пульт и кладёт одноразовые команды процессу показа."""

    def __init__(
        self,
        api: TelegramApi,
        chat_id: str,
        path: Path | None = None,
        *,
        remember: bool = True,
    ) -> None:
        self._api = api
        self._chat_id = chat_id
        self._path = path or Path(f"/tmp/torrcast-telegram-{os.getuid()}.ctl")
        self._message_path = (
            self._path.with_suffix(self._path.suffix + ".message") if remember else None
        )
        self._message_id = self._remembered_message()
        self._text = ""
        self._lock = threading.Lock()
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
        """Создать пульт или поправить его прежнее сообщение на месте.

        Отказ Telegram не прячется за нулевым номером: он поднимается
        (:class:`_TelegramError`), чтобы наблюдатель назвал его в следе.
        """
        with self._lock:
            if self._message_id:
                if text != self._text:
                    result = self._api.edit(self._chat_id, self._message_id, text, self.buttons())
                    if getattr(result, "status", 200) != 200:
                        raise _refused(result)
                    self._text = text
                return self._message_id
            result = self._api.post(self._chat_id, text, self.buttons())
            if result.status != 200 or not isinstance(result.value, dict):
                raise _refused(result)
            self._message_id = int(result.value.get("message_id", 0))
            self._text = text
            if self._message_id and self._message_path is not None:
                self._message_path.write_text(str(self._message_id), encoding="ascii")
            return self._message_id

    def clean(self) -> None:
        """Убрать пульт, не связывая успех остановки с правами Telegram."""
        with self._lock:
            if not self._message_id:
                return
            deleted = False
            with suppress(Exception):
                result = self._api.delete(self._chat_id, self._message_id)
                deleted = getattr(result, "status", 200) == 200
            if not deleted:
                with suppress(Exception):
                    self._api.edit(self._chat_id, self._message_id, self._stopped_text(), None)
            self._message_id = 0
            self._text = ""
            if self._message_path is not None:
                self._message_path.unlink(missing_ok=True)

    def _remembered_message(self) -> int:
        """Вернуть пульт прежнего процесса, если его номер записан целым."""
        if self._message_path is None:
            return 0
        with suppress(OSError, ValueError):
            return int(self._message_path.read_text(encoding="ascii"))
        return 0

    @staticmethod
    def _stopped_text() -> str:
        """Назвать мёртвый пульт каталогом продукта без цикла импортов."""
        from torrcast.domain.catalogs.phrase import phrase

        return phrase("telegram.nothing_playing")

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
