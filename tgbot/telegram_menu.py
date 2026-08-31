"""Inline-представление того же списка картин, который рисует сценарий выбора."""

from __future__ import annotations

import re
from collections.abc import Callable

from tgbot.telegram_api import TelegramApi

_NUMBER = re.compile(r"^\s*(\d+)[.)]\s*")


class TelegramMenu:
    """Меню Telegram: текст показывается один раз, ответ переписывает его на месте."""

    live = False

    def __init__(
        self,
        api: TelegramApi,
        chat_id: str,
        callback: Callable[[int, int], str],
        cancel: dict[str, str] | None = None,
    ) -> None:
        self._api = api
        self._chat_id = chat_id
        self._callback = callback
        #: Готовая кнопка отмены: карточка её только ставит, а надпись и адрес ответа
        #: знает окружение выбора - у него номер вопроса, а язык называет надписи
        #: единый держатель продукта (:mod:`tgbot.i18n`).
        self._cancel = cancel
        self._lines: list[str] = []
        self._buttons: list[list[dict[str, str]]] = []
        self.message_id = 0

    def show(self, lines: list[str]) -> None:
        """Показать строки и сделать строку каждой картины кнопкой."""
        self._lines = lines
        heads = [(int(match.group(1)), line) for line in lines if (match := _NUMBER.match(line))]
        self._buttons = [
            [{"text": line, "callback_data": self._callback(number, 0)}] for number, line in heads
        ]
        if self._cancel is not None:
            # 🔴 TC-926. Отмена - последней строкой ПОД списком: человек дочитывает список
            # сверху вниз, и выход из вопроса стоит там, где он кончил читать.
            self._buttons.append([self._cancel])
        self.message_id = self._api.send(self._chat_id, "\n".join(lines), self._buttons)

    def note(self, line: str) -> None:
        """Дополнить карточку честной строкой, не создавая соседнее сообщение."""
        self._lines.append(line)
        self._api.edit(self._chat_id, self.message_id, "\n".join(self._lines), self._buttons)

    def chosen(self, number: int) -> None:
        """Оставить выбранную строку в той же карточке и убрать клавиатуру."""
        text = ""
        for line in self._lines:
            match = _NUMBER.match(line)
            if match and int(match.group(1)) == number:
                text = line
                break
        self._api.edit(self._chat_id, self.message_id, text)

    def redraw(self, index: int, line: str) -> None:
        """Справка заранее ждётся сценарием, поэтому дорисовывать здесь нечего."""

    def close(self) -> None:
        """Закрытие не удаляет карточку из истории чата."""
