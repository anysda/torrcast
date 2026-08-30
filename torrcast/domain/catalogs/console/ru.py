"""Русские надписи кластера консольного ввода-вывода."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера консольного ввода-вывода."""
    return {
        "console.need_number": "нужен номер от 1 до {count}",
        "console.need_number_no_terminal": "нужен номер от 1 до {count}, а терминала нет",
        "console.no_terminal_default": "(терминала нет - беру по умолчанию)",
        "console.seconds": "с",
    }
