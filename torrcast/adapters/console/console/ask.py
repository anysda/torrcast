"""Вопрос с номерами: цифра или Enter, а без терминала - без второго круга.

Зовут его меню отбора, меню озвучек и консоль команд за портом."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.adapters.console.console import stdin_is_tty as _tty
from torrcast.adapters.console.console.ask_line import ask_line


def ask(
    question: str,
    count: int,
    default: int | None = 1,
    tty: Callable[[], bool] | None = None,
    read: Callable[[str], str] | None = None,
) -> int:
    """Вопрос с номерами: принимает и цифру, и пустой Enter - когда дефолт есть.

    ``default=None`` - дефолта нет нарочно: любой автовыбор тут был бы подменой картины
    (:func:`~torrcast.usecases.choice.part_one_swap.part_one_swap`), и номер обязан назвать сам
    человек. Пустой Enter такой ответом не считается - вопрос повторяется.

    Терминал и чтение строки едут дальше в свободный ответ теми же параметрами: круг
    вопросов тут один, и внешний мир у него один на оба вопроса.
    """
    has_tty = _tty.stdin_is_tty if tty is None else tty
    prompt = f"{question} [{default}]" if default is not None else question
    while True:
        answer = ask_line(prompt, tty=has_tty, read=read)
        if not answer and default is not None:
            return default
        if answer.isdigit() and 1 <= int(answer) <= count:
            return int(answer)
        print(f"нужен номер от 1 до {count}")
        if not has_tty():  # спросить некого - вторым кругом висеть не будем
            if default is None:
                raise EOFError(f"нужен номер от 1 до {count}, а терминала нет")
            return default
