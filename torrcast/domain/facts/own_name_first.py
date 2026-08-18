"""Порядок кандидатов прямой выборки; зовёт выборка статьи по имени."""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.json_map import json_map
from torrcast.domain.json_value import JsonValue
from torrcast.domain.slugify import slugify


def _own_name_first(pages: Sequence[JsonValue], title: str) -> list[JsonValue]:
    """Кандидаты прямой выборки: сначала статьи, названные ИМЕНЕМ запроса.

    Уточнение в скобках порядка не задаёт: «девять (мультфильм)» стоит в перечне раньше
    «девять (фильм)» просто по алфавиту, и первая же киношная статья побеждала - справка
    отвечала про мультфильм «9», когда спрашивали «Девять». Между тем перенаправление
    «девять (мультфильм)» → ``9 (мультфильм, 2009)`` - это уже ДРУГОЕ имя: статья
    подписана не так, как спросили. Статья же «Девять (фильм)» названа ровно спрошенным
    словом, и её слово о картине с этим именем сильнее.

    Переименованные перенаправления («Уэнсдей» → «Уэнздей») ничего не теряют: они просто
    идут следом, и без тёзок впереди выбор остаётся прежним. Меняется ровно один случай -
    когда про кино есть и тёзка, и одноимённая подмена: раньше побеждал порядок уточнений,
    теперь - имя.
    """
    wanted = slugify(title)

    def own(page: JsonValue) -> bool:
        heading = str(json_map(page).get("title") or "")
        return bool(wanted) and slugify(heading.split(" (")[0]) == wanted

    return sorted(pages, key=lambda page: not own(page))
