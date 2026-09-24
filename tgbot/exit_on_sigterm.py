"""Чистый выход долгоживущего бота по сигналу менеджера служб."""

from __future__ import annotations

import signal


def exit_on_sigterm() -> None:
    """Поставить внешний обработчик, к которому команда вернёт SIGTERM после уборки."""

    def leave(_number: int, _frame: object) -> None:
        raise SystemExit

    signal.signal(signal.SIGTERM, leave)
