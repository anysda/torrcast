"""Зеркало человеческого ввода Telegram для выбора картины."""

from __future__ import annotations

from typing import cast

import pytest

from tests.test_telegram_menu import _Api
from tests.usecases.choice.world import parts
from tgbot.i18n import i18n
from tgbot.telegram_api import TelegramApi
from tgbot.telegram_choice_environment import TelegramChoiceEnvironment
from torrcast.domain.cancelled_error import CancelledError
from torrcast.usecases.choice.default_line import default_line


def test_callback_answers_the_same_question_that_drew_the_menu() -> None:
    api = _Api()
    environment = TelegramChoiceEnvironment(cast(TelegramApi, api), "-100")
    environment.begin(7)
    menu = environment.menu()
    menu.show(["1. Мумия (1932)", "2. Мумия (2026)"])
    callback = cast(list[list[dict[str, str]]], api.sent[0][2])[1][0]["callback_data"]

    assert environment.accept(callback, 42)
    assert environment.ask("Что смотрим?", 2) == 2
    assert not environment.accept(callback, 41)


def test_cancel_wakes_the_question_with_its_own_kind_not_with_a_refusal(
    _russian_product: None,
) -> None:
    """🔴 TC-926. Кнопка отмены выводит ожидание своим родом, а не отказом «не нашли».

    Отказ уехал бы в чат строкой «Каст не начался: 1» - на своё же нажатие. Отмену
    принимает ровно НЫНЕШНЯЯ карточка: чужой номер сообщения ей не указ, иначе кнопка
    старого меню снимала бы новый вопрос.
    """
    api = _Api()
    environment = TelegramChoiceEnvironment(cast(TelegramApi, api), "-100")
    environment.begin(7)
    menu = environment.menu()
    menu.show(["1. Мумия (1932)", "2. Мумия (2026)"])
    buttons = cast(list[list[dict[str, str]]], api.sent[0][2])
    drop = buttons[-1][0]

    assert drop["text"] == i18n("cancel")
    assert not environment.cancel(drop["callback_data"], 41), "чужая карточка вопрос не снимает"
    assert environment.cancel(drop["callback_data"], 42)

    with pytest.raises(CancelledError):
        environment.ask("Что смотрим?", 2)

    pick = buttons[0][0]["callback_data"]
    assert not environment.accept(pick, 42), "вопрос снят - отвечать на него уже нечему"


def test_the_enter_hint_is_dropped_where_there_is_no_keyboard() -> None:
    """🔴 TC-926. Подсказка про Enter - речь терминала: в чат она не уходит вовсе.

    Строка берётся у самого продукта (:func:`default_line`), а не переписывается сюда
    руками: перепиши её - и зеркало проверяло бы свою редакцию, а не ту, что печатается.
    Соседняя честная строка стража при этом доезжает: гасится ровно подсказка.
    """
    api = _Api()
    environment = TelegramChoiceEnvironment(cast(TelegramApi, api), "-100")
    environment.begin(7)
    hint = default_line(parts(("Мумия", 1932, 47), ("Мумия", 2026, 604)), 1)

    environment.write(hint)

    assert hint.startswith("Enter"), "гасим ровно ту строку, которую печатает продукт"
    assert api.sent == [], "в чате клавиатуры нет - и подсказке про неё места нет"

    environment.write("беру «Мумия (2026)» - самая живая из одноимённых")

    assert [text for _chat, text, _buttons in api.sent] == [
        "беру «Мумия (2026)» - самая живая из одноимённых"
    ]


def test_search_answer_replies_to_the_command_without_buttons() -> None:
    api = _Api()
    environment = TelegramChoiceEnvironment(cast(TelegramApi, api), "-100")
    environment.begin(7)
    environment.write("играю «Блич (2004)»; всего подошло картин 2; другая: cast блич --menu")

    assert api.sent == [
        ("-100", "играю «Блич (2004)»; всего подошло картин 2; другая: cast блич --menu", None)
    ]
    assert api.replied == [7]


def test_the_ended_show_retires_its_own_command_and_not_the_running_dialog() -> None:
    """Конец показа снимает сообщение СВОЕЙ команды, чужая нынешняя остаётся.

    Наблюдатель зовёт уборку с номером, запомненным на старте кончившегося показа:
    если чат уже заняла следующая команда, её сообщение - не след старого показа.
    """
    api = _Api()
    environment = TelegramChoiceEnvironment(cast(TelegramApi, api), "-100")
    environment.begin(7)

    environment.clean_command(7)
    assert api.deleted == [7]
    assert environment.command_id() == 0, "снятая команда не убирается дважды"

    # Щель между показами: команда 9 уже заняла чат, а кончился показ команды 7.
    environment.begin(7)
    environment.begin(9)
    environment.clean_command(7)

    assert api.deleted == [7, 7]
    assert environment.command_id() == 9, "чужая нынешняя команда остаётся нетронутой"

    environment.clean_command(9)
    environment.clean()

    assert api.deleted == [7, 7, 9], "обе команды сняты своими концами, повторной уборки нет"
