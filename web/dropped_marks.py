"""Отметка тела полок: какие плитки заход этого правила честно назвал «не играет».

«Не играет» памяти приговоров не имеет (:class:`web.shelf_playable.ShelfPlayable`,
TC-1343): каждый заход спрашивает плитку заново. Но заход, которому TorrServer не
ответил, получает на всё «не знаю», а «не знаю» плитку на полке держит
(:func:`web.shelf_tiles._covered`). Без отметки такой заход ставил бы обратно плитки,
которые прошлый заход с экрана честно снял: незнание меняло бы экран так же, как приговор.

Отметка симметрична правилу «не знаю не снимает»: «не знаю» и не возвращает. Вернуть
плитку может только приговор «играет» - ожившая раздача на полку возвращается, вечного
«негоден» нет. Память сама ограничена: ключ держится, пока заход его спрашивает и
слышит «не играет» или «не знаю», а не спрошенный ключ забывается.
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.json_value import JsonValue
from web.drop_count import DropCount

#: Поле тела полок: ключи плиток каждой полки, честно снятых заходом этого правила.
DROPPED: Final = "dropped"


def dropped_marks(body: dict[str, JsonValue], shelf: str, drops: DropCount) -> dict[str, JsonValue]:
    """Отметка тела после захода ``drops`` по полке ``shelf``; прочие полки как были."""
    marks = body.get(DROPPED)
    old = marks if isinstance(marks, dict) else {}
    keys = old.get(shelf)
    known = {key for key in keys if isinstance(key, str)} if isinstance(keys, list) else set()
    gone: list[JsonValue] = [*sorted(drops.dropped_keys | (known & drops.unknown_keys))]
    return {**old, shelf: gone}


__all__ = ["DROPPED", "dropped_marks"]
