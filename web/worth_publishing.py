"""Публиковать ли собранное тело полок вместо уже показанного (TC-1343).

Прежняя абсолютная планка полноты защищала старое тело сравнением с числом плиток.
После отсева неиграющих плиток (:mod:`web.shelf_playable`) настоящие полки законно
стали короче неё, и одна неудачная фоновая сборка (TorrServer лёг, индексер замолчал)
могла бы молча перезаписать рабочую полку пустой. Защита здесь читает ПРЕЖНЕЕ тело и
его относительное усыхание, а не планку наличия :data:`web.min_tiles.FLOOR`.
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.json_value import JsonValue
from web.built_by_rule import built_by_rule
from web.drop_count import DropCount

#: Новая полка не вправе усохнуть больше чем вдвое против прежней той же версии отбора:
#: половина и ниже - потеря БОЛЬШИНСТВА содержимого, видимая владельцу при любой причине
#: сжатия, а не честный отсев мусора. Пустая новая полка при непустой прежней сама попадает
#: под эту планку (0 меньше половины любого ``old >= 1``) - отдельного правила не нужно.
SHRINK_FLOOR: Final = 0.5
#: Доля честно отброшенных «не играет» среди честно проверенных (без «не знаю» ни в
#: числителе, ни в знаменателе), выше которой сборка не публикуется. Замер живого стенда
#: TC-1343 дал ~20.9% (27 из 129) при исправном TorrServer - это норма; «половина и
#: больше» владелец назвал прямой поломкой стенда. 0.35 лежит с запасом над нормой и с
#: запасом до названной поломки.
MASS_DROP: Final = 0.35


def worth_publishing(
    current: dict[str, JsonValue], best: dict[str, JsonValue], drops: DropCount
) -> bool:
    """Стоит ли заменить прежнее тело новым: без предшественника - да, иначе - две пробы.

    Без годного предшественника (иное правило отбора или холодный старт) защищать
    нечего - первая сборка правила публикуется как есть, даже пустая: без неё сайт
    остаётся в ``X-Torrcast-Partial``, что честнее опубликованного мусора.

    Дальше - две защиты от одного неудачного прогона: усохшая больше чем вдвое полка
    (:data:`SHRINK_FLOOR`, покрывает и пустую полку при непустой прежней) и доля
    честных «не играет» выше нормы (:data:`MASS_DROP`).
    """
    if not built_by_rule(current):
        return True
    for shelf in ("fresh", "popular"):
        old, new = _shelf_len(current, shelf), _shelf_len(best, shelf)
        if old and new < old * SHRINK_FLOOR:
            return False
    return drops.ratio <= MASS_DROP


def _shelf_len(body: dict[str, JsonValue], shelf: str) -> int:
    rows = body.get(shelf)
    return len(rows) if isinstance(rows, list) else 0


__all__ = ["MASS_DROP", "SHRINK_FLOOR", "worth_publishing"]
