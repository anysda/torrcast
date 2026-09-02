"""Зеркало inline-меню Telegram и его ответа на месте."""

from __future__ import annotations

from typing import cast

from tgbot.telegram_api import TelegramApi
from tgbot.telegram_menu import TelegramMenu
from tgbot.transport import _TelegramResult


class _Api:
    """Записывает вызовы Bot API без сети."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, object]] = []
        self.edited: list[tuple[str, int, str, object]] = []
        self.replied: list[int | None] = []
        self.deleted: list[int] = []

    def send(
        self,
        chat_id: str,
        text: str,
        buttons: object = None,
        reply_to_message_id: int | None = None,
    ) -> int:
        self.replied.append(reply_to_message_id)
        self.sent.append((chat_id, text, buttons))
        return 42

    def post(
        self,
        chat_id: str,
        text: str,
        buttons: object = None,
        reply_to_message_id: int | None = None,
    ) -> _TelegramResult:
        self.replied.append(reply_to_message_id)
        self.sent.append((chat_id, text, buttons))
        return _TelegramResult(200, "", {"message_id": 42})

    def delete(self, _chat_id: str, message_id: int) -> object:
        self.deleted.append(message_id)
        return object()

    def edit(self, chat_id: str, message_id: int, text: str, buttons: object = None) -> object:
        self.edited.append((chat_id, message_id, text, buttons))
        return object()


def test_choice_edits_the_menu_instead_of_sending_a_second_message() -> None:
    api = _Api()
    assert callable(api.send)
    menu = TelegramMenu(cast(TelegramApi, api), "-100", lambda number, _mid: f"pick:x:{number}")

    menu.show(["1. Мумия (1932)", "  первое кино", "2. Мумия (2026)"])
    menu.chosen(2)

    assert len(api.sent) == 1
    assert api.edited == [("-100", 42, "2. Мумия (2026)", None)]
    assert api.sent[0][2] == [
        [{"text": "1. Мумия (1932)", "callback_data": "pick:x:1"}],
        [{"text": "2. Мумия (2026)", "callback_data": "pick:x:2"}],
    ]


def test_the_cancel_button_stands_under_the_list_and_survives_a_note() -> None:
    """🔴 TC-926. Отмена - последней кнопкой ПОД списком, а не среди картин.

    Строка стража, дописанная в карточку, кнопки не теряет: без отмены в этой правке
    человек остался бы с картой без выхода ровно после первой же честной строки.
    """
    api = _Api()
    menu = TelegramMenu(
        cast(TelegramApi, api),
        "-100",
        lambda number, _mid: f"pick:x:{number}",
        cancel={"text": "Отмена", "callback_data": "drop:x"},
    )

    menu.show(["1. Мумия (1932)", "2. Мумия (2026)"])
    menu.note("взята живейшая")

    assert api.sent[0][2] == [
        [{"text": "1. Мумия (1932)", "callback_data": "pick:x:1"}],
        [{"text": "2. Мумия (2026)", "callback_data": "pick:x:2"}],
        [{"text": "Отмена", "callback_data": "drop:x"}],
    ]
    assert api.edited[0][3] == api.sent[0][2], "дописанная строка кнопку отмены не съедает"

    menu.chosen(2)

    assert api.edited[-1] == ("-100", 42, "2. Мумия (2026)", None), "отвечено - кнопок нет"


def test_guard_note_is_added_to_the_existing_card_with_buttons() -> None:
    api = _Api()
    menu = TelegramMenu(cast(TelegramApi, api), "-100", lambda number, _mid: str(number))

    menu.show(["1. Блич (2004)", "2. Блич (2018)"])
    menu.note("взята живейшая; другую выберите кнопкой ниже")

    assert len(api.sent) == 1
    assert len(api.edited) == 1
    assert api.edited[0][1] == 42
    assert api.edited[0][2].endswith("другую выберите кнопкой ниже")
    assert api.edited[0][3] is not None
