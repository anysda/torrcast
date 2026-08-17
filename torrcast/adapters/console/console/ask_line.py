"""Свободный ответ человека: Enter берёт дефолт, а без терминала - берёт сразу.

Зовут его вопрос с номерами и консоль команд за портом."""

from __future__ import annotations

from torrcast.adapters.console import console as _console


def ask_line(question: str, default: str = "") -> str:
    """Свободный ответ. Enter — дефолт; терминала нет — тоже дефолт, и **без ожидания**.

    Вечное ожидание на пайпе (наблюдалось 180 с) — это не «строгость», а зависший
    сценарий: спросить всё равно некого.
    """
    prompt = f"{question}: "
    if not _console.stdin_is_tty():
        print(f"{prompt}{default or '(терминала нет - беру по умолчанию)'}", flush=True)
        return _console.clean(default).casefold()
    try:
        raw = input(prompt)
    except EOFError:
        print(flush=True)
        return _console.clean(default).casefold()
    answer = _console.clean(raw).casefold()
    return answer or _console.clean(default).casefold()
