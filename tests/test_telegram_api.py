"""Зеркало узкого клиента Telegram Bot API."""

from typing import cast

from tgbot.telegram_api import TelegramApi
from tgbot.transport import _TelegramClient, _TelegramResult


class _Client:
    """Возвращает заданные ответы и запоминает метод с параметрами."""

    def __init__(self, answer: _TelegramResult) -> None:
        self.answer = answer
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call(self, method: str, **params: object) -> _TelegramResult:
        self.calls.append((method, params))
        return self.answer


def test_edit_uses_edit_message_text_with_an_empty_keyboard() -> None:
    api = TelegramApi("secret")
    client = _Client(_TelegramResult(200, value=True))
    api._client = cast(_TelegramClient, client)

    api.edit("-100", 42, "выбрано")

    assert client.calls[0][0] == "editMessageText"
    assert client.calls[0][1]["message_id"] == 42
    assert client.calls[0][1]["reply_markup"] == '{"inline_keyboard": []}'


def test_send_can_reply_and_delete_uses_the_bot_api_method() -> None:
    api = TelegramApi("secret")
    client = _Client(_TelegramResult(200, value={"message_id": 18}))
    api._client = cast(_TelegramClient, client)

    assert api.send("-100", "поиск", reply_to_message_id=7) == 18
    api.delete("-100", 18)

    assert client.calls[0][0] == "sendMessage"
    assert client.calls[0][1]["reply_to_message_id"] == 7
    assert client.calls[1] == ("deleteMessage", {"chat_id": "-100", "message_id": 18})
