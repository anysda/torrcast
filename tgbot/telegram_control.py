"""Inline-пульт текущего показа через ручку владеющего процесса."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from tgbot.control_message import ControlMessage
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
        poster: Callable[[], bytes | None] | None = None,
    ) -> None:
        self._api = api
        self._chat_id = chat_id
        self._poster = poster
        self._path = path or Path(f"/tmp/torrcast-telegram-{os.getuid()}.ctl")
        self._kept = ControlMessage(
            self._path.with_suffix(self._path.suffix + ".message") if remember else None
        )
        self._message_id, self._photo = self._kept.read()
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

        Обложка едет ТОЙ ЖЕ посылкой, что и кнопки, а не картинкой рядом: человек
        видит одну карточку показа. Обложки нет - пульт остаётся прежним текстовым
        сообщением (:class:`tgbot.playing_poster.PlayingPoster`): кнопки нужны ему
        всегда, а картинка - когда она есть.

        Отказ Telegram не прячется за нулевым номером: он поднимается
        (:class:`_TelegramError`), чтобы наблюдатель назвал его в следе.
        """
        with self._lock:
            if self._message_id:
                if not self._photo and self._dressed(text):
                    return self._message_id
                if text != self._text:
                    self._rewrite(text)
                return self._message_id
            body = self._cover()
            if body is not None and self._opened(text, body):
                return self._message_id
            result = self._api.post(self._chat_id, text, self.buttons())
            if result.status != 200 or not isinstance(result.value, dict):
                raise _refused(result)
            self._remember(int(result.value.get("message_id", 0)), text, photo=False)
            return self._message_id

    def _rewrite(self, text: str) -> None:
        """Поправить шапку на месте: у картинки правится подпись, у текста - текст."""
        if self._photo:
            result = self._api.edit_caption(self._chat_id, self._message_id, text, self.buttons())
        else:
            result = self._api.edit(self._chat_id, self._message_id, text, self.buttons())
        if getattr(result, "status", 200) != 200:
            raise _refused(result)
        self._text = text

    def _dressed(self, text: str) -> bool:
        """Одеть висящий текстовый пульт в доехавшую обложку; нечем - оставить как есть.

        Обложка приходит из сети позже первых кнопок, а текстовое сообщение картинкой
        не становится правкой - только заменой. Замена идёт ОДИН раз за показ и только
        на готовые байты: не вышло - человек теряет картинку, а не кнопки.
        """
        body = self._cover()
        if body is None:
            return False
        standing, self._message_id = self._message_id, 0
        if not self._opened(text, body):
            self._message_id = standing
            return False
        with suppress(Exception):
            self._api.delete(self._chat_id, standing)
        return True

    def _opened(self, text: str, body: bytes) -> bool:
        """Открыть пульт картинкой с подписью; Telegram отказал - вернуть ложь.

        Отказ тут НЕ поднимается: за картинкой стоит текстовый пульт, и терять из-за
        неё кнопки нельзя. Мёртвый токен назовёт себя следом, на текстовой посылке.
        """
        result = self._api.photo(self._chat_id, body, text, self.buttons())
        if result.status != 200 or not isinstance(result.value, dict):
            return False
        number = int(result.value.get("message_id", 0))
        if not number:
            return False
        self._remember(number, text, photo=True)
        return True

    def _cover(self) -> bytes | None:
        """Байты обложки играющего; источник молчит или падает - ``None``."""
        with suppress(Exception):
            return self._poster() if self._poster else None
        return None

    def _remember(self, number: int, text: str, *, photo: bool) -> None:
        """Запомнить пульт: его номер переживает перезапуск процесса показа."""
        self._message_id = number
        self._text = text
        self._photo = photo
        self._kept.write(number, photo=photo)

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
                    self._erase()
            self._message_id = 0
            self._text = ""
            self._photo = False
            self._kept.forget()

    def _erase(self) -> None:
        """Погасить неудалённый пульт: у картинки гасится подпись, у текста - текст."""
        if self._photo:
            self._api.edit_caption(self._chat_id, self._message_id, self._stopped_text(), None)
            return
        self._api.edit(self._chat_id, self._message_id, self._stopped_text(), None)

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
