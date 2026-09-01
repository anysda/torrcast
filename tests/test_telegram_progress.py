"""Запуск из чата говорит текущую ступень одним редким сообщением."""

from typing import cast

import pytest

from tgbot.telegram_api import TelegramApi
from tgbot.telegram_progress import TelegramProgress


class _Api:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.edited: list[tuple[int, str]] = []
        self.deleted: list[int] = []

    def send(self, _chat: str, text: str, _buttons: object = None) -> int:
        message_id = 70 + len(self.sent)
        self.sent.append((message_id, text))
        return message_id

    def edit(self, _chat: str, message_id: int, text: str, _buttons: object = None) -> object:
        self.edited.append((message_id, text))
        return object()

    def delete(self, _chat: str, message_id: int) -> object:
        self.deleted.append(message_id)
        return object()


def test_phases_notes_and_failure_edit_one_message(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _Api()
    now = [10.0]
    board = TelegramProgress(cast(TelegramApi, api), "-100", tick=60, clock=lambda: now[0])

    first = board.new()
    first.phase("поиск «мумия»")
    now[0] = 20.0
    first.note("видео тяжело приёмнику, перекодирую целиком")
    first.stop()
    now[0] = 30.0
    board.new().phase("упаковка")
    board.finish("Каст не начался: телевизор не ответил")

    assert api.sent == [(70, "поиск «мумия»... 0 s")]
    assert {message_id for message_id, _text in api.edited} == {70}
    assert "перекодирую целиком" in api.edited[0][1]
    assert api.edited[-1] == (70, "Каст не начался: телевизор не ответил")
