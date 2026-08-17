"""Вопрос с номерами: цифра или Enter, а без терминала - без второго круга.

Зовут его меню отбора, меню озвучек и консоль команд за портом."""

from __future__ import annotations

from torrcast.adapters.console import console as _console


def ask(question: str, count: int, default: int | None = 1) -> int:
    """Вопрос с номерами: принимает и цифру, и пустой Enter - когда дефолт есть.

    ``default=None`` - дефолта нет нарочно: любой автовыбор тут был бы подменой картины
    (:func:`~torrcast.cli.part_one_swap`), и номер обязан назвать сам человек. Пустой
    Enter такой ответом не считается - вопрос повторяется.
    """
    prompt = f"{question} [{default}]" if default is not None else question
    while True:
        answer = _console.ask_line(prompt)
        if not answer and default is not None:
            return default
        if answer.isdigit() and 1 <= int(answer) <= count:
            return int(answer)
        print(f"нужен номер от 1 до {count}")
        if not _console.stdin_is_tty():  # спросить некого - вторым кругом висеть не будем
            if default is None:
                raise EOFError(f"нужен номер от 1 до {count}, а терминала нет")
            return default
