"""Сторож на класс дефекта: `hidden` в js обязан ПРЯТАТЬ.

`hidden` работает одним-единственным правилом `[hidden] { display: none }` из таблицы
самого браузера, а она проигрывает любому авторскому классу той же силы. Стоит классу
элемента объявить `display`, и `node.hidden = true` перестаёт значить что-либо: плашка
«on TV» висела на экране во всех трёх состояниях подряд - в простое, при показе во
вкладке и на ТВ (TC-1149, замер на стенде `.104` 10-09-2026), а рядом с ней всегда
торчали «На ТВ» в карточке и «Следующая» на панели (у обеих класс `.tc-btn` с
`display: inline-flex`).

Ловить это поштучно нечем: правило прячется не в js, а в чужом файле, и следующий
класс с `display` ломает следующую спрятанную вещь молча. Порог тут не двигается -
проверяется наличие самого правила.
"""

from __future__ import annotations

import re
from pathlib import Path

STYLE = Path(__file__).resolve().parents[1] / "web" / "static" / "style.css"

#: Сила правила: без `!important` оно проигрывает классу той же силы, объявленному ниже.
RULE = re.compile(r"\[hidden\]\s*\{[^}]*display\s*:\s*none\s*!important", re.IGNORECASE)

#: Что js прячет атрибутом: каждая такая строка держится правилом выше.
HIDES = re.compile(r"\.hidden\s*=")


def test_the_sheet_makes_the_hidden_attribute_win() -> None:
    assert RULE.search(STYLE.read_text(encoding="utf-8")), (
        "в style.css нет правила [hidden] { display: none !important }: "
        "любой класс с display снова сделает hidden пустым словом"
    )


def test_the_pages_do_hide_things_by_the_attribute() -> None:
    """Правило выше не украшение: страницы прячут атрибутом, а не классом."""
    users = [
        js.name
        for js in sorted(STYLE.parent.glob("*.js"))
        if HIDES.search(js.read_text(encoding="utf-8"))
    ]
    assert users, "ни один модуль страницы не прячет атрибутом - сторож стережёт пустоту"
