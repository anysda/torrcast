"""Сторож: в надписях продукта (`torrcast/domain/catalogs/`) длинных тире нет.

Только этого дерева касается - `tgbot/` и его тесты сюда не входят: там длинное тире
несущее (Telegram-клиент подменяет ``--menu`` на ``—menu``, и продукт лечит это обратно,
:mod:`tgbot.restore_flag_dashes`), а не грязь из макета.
"""

from __future__ import annotations

from pathlib import Path

_LONG_DASHES = ("—", "–", "―")  # — – ―
_ROOT = Path(__file__).parents[2] / "torrcast" / "domain" / "catalogs"


def test_no_long_dash_anywhere_under_domain_catalogs() -> None:
    offenders = [
        f"{path}:{number}"
        for path in _ROOT.rglob("*.py")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if any(dash in line for dash in _LONG_DASHES)
    ]

    assert offenders == []
