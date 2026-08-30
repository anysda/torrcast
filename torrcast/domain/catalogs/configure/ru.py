"""Русские надписи кластера настройки телевизора."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера настройки телевизора."""
    return {
        "configure.headless_note": " (headless-приёмник, каста наружу нет)",
        "configure.tv_line": "ТВ: {name}{address}{note}",
        "configure.no_receivers_found": (
            "приёмников в сети не нашёл - телевизор включён и в той же сети? "
            "адрес можно задать и руками: cast --tv <ip>"
        ),
        "configure.found_no_terminal": (
            "нашёл приёмников: {count}, а терминала нет - вслепую не выбираю; "
            "назови адрес сам: cast --tv <ip>"
        ),
        "configure.which_tv": "Какой телевизор?",
    }
