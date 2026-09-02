"""Узкий клиент Bot API для живого цикла бота."""

from __future__ import annotations

import json
from typing import Any

from tgbot.transport import _TelegramClient, _TelegramResult


class TelegramApi:
    """Называет операции Telegram, не размазывая JSON по обработчикам."""

    def __init__(self, token: str, proxy: str = "", timeout: float = 20.0) -> None:
        self._client = _TelegramClient(token, proxy, timeout)

    def updates(self, offset: int, timeout: int = 20) -> list[dict[str, Any]]:
        """Получить следующую пачку обновлений."""
        result = self._client.call("getUpdates", offset=offset, timeout=timeout)
        if result.status != 200 or not isinstance(result.value, list):
            return []
        return [item for item in result.value if isinstance(item, dict)]

    def send(
        self,
        chat_id: str,
        text: str,
        buttons: list[list[dict[str, str]]] | None = None,
        reply_to_message_id: int | None = None,
    ) -> int:
        """Послать одно тихое сообщение и вернуть его номер."""
        result = self.post(chat_id, text, buttons, reply_to_message_id)
        if isinstance(result.value, dict):
            return int(result.value.get("message_id", 0))
        return 0

    def post(
        self,
        chat_id: str,
        text: str,
        buttons: list[list[dict[str, str]]] | None = None,
        reply_to_message_id: int | None = None,
    ) -> _TelegramResult:
        """Послать одно тихое сообщение и вернуть весь исход, не только номер.

        Пульту показа нужен статус отказа: беда сети и 401 - разные беды, а голый
        номер сообщения прячет обе за нулём (:class:`tgbot.telegram_control.TelegramControl`).
        """
        params: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
            "disable_notification": True,
        }
        if buttons is not None:
            params["reply_markup"] = json.dumps({"inline_keyboard": buttons}, ensure_ascii=False)
        if reply_to_message_id is not None:
            params["reply_to_message_id"] = reply_to_message_id
        return self._client.call("sendMessage", **params)

    def edit(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> _TelegramResult:
        """Переписать то же сообщение, при необходимости сохранив кнопки."""
        markup = {"inline_keyboard": buttons or []}
        return self._client.call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=json.dumps(markup, ensure_ascii=False),
        )

    def answer(self, callback_id: str, text: str = "") -> _TelegramResult:
        """Погасить часы callback без нового сообщения."""
        return self._client.call("answerCallbackQuery", callback_query_id=callback_id, text=text)

    def delete(self, chat_id: str, message_id: int) -> _TelegramResult:
        """Попытаться удалить сообщение; исход уборки решает вызывающий код."""
        return self._client.call("deleteMessage", chat_id=chat_id, message_id=message_id)
