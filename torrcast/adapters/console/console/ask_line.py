"""Свободный ответ человека: Enter берёт дефолт, а без терминала - берёт сразу.

Зовут его вопрос с номерами и консоль команд за портом."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.adapters.console import console as _console


def ask_line(
    question: str,
    default: str = "",
    tty: Callable[[], bool] | None = None,
    read: Callable[[str], str] | None = None,
) -> str:
    """Свободный ответ. Enter — дефолт; терминала нет — тоже дефолт, и **без ожидания**.

    Вечное ожидание на пайпе (наблюдалось 180 с) — это не «строгость», а зависший
    сценарий: спросить всё равно некого.

    Обе связи с внешним миром - «есть ли терминал» и «чем читать строку» - названы
    параметрами: спрашивающий вправе назвать их сам, и меряются они подставленной парой.
    ``None`` значит «взять живые»: консоль спрашивают из десятка мест, и передавать туда
    нечего.
    """
    has_tty = _console.stdin_is_tty if tty is None else tty
    line = input if read is None else read
    prompt = f"{question}: "
    if not has_tty():
        print(f"{prompt}{default or '(терминала нет - беру по умолчанию)'}", flush=True)
        return _console.clean(default).casefold()
    try:
        raw = line(prompt)
    except EOFError:
        print(flush=True)
        return _console.clean(default).casefold()
    answer = _console.clean(raw).casefold()
    return answer or _console.clean(default).casefold()
