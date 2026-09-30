"""Обложки полки главной: быстрый путь поиска, а байты - по мере приезда, без ожидания пачки.

Прежде полка брала :meth:`hass.hit_posters.HitPosters.settled`: приговор фоновым путём и
ожидание байтов всей пачки до 30 с, и только после этого - приговоры «играет ли». Холодный
заход полок (:mod:`web.shelf_pass`) спрашивает обложки тем же путём, что и видимая выдача
поиска (``urgent``: гонка источников, опоздавшие ложатся следом, :mod:`hass.both_posters`), и
показывает плитку, как только её байты легли. Поиск этот модуль не трогает: его поведение
задаётся только его собственными вызовами :class:`~hass.hit_posters.HitPosters`.
"""

from __future__ import annotations

from dataclasses import dataclass

from hass.hit_ask import _about, _name
from hass.hit_posters import FIELD, HitPosters, hits
from hass.serial_parent_posters import _ready_posters, serial_parent_posters
from torrcast.domain.json_value import JsonValue


@dataclass(frozen=True)
class ShelfPosters:
    """Обложки полки через ``owner``; в бою - общий :data:`hass.hit_posters.hits`."""

    owner: HitPosters = hits

    def ask(self, results: list[JsonValue]) -> list[JsonValue]:
        """Спросить обложки всей пачки; вернуть записи, у которых байты уже здесь."""
        self.owner.offer(results, urgent=True)
        return self.landed(results)

    def landed(self, results: list[JsonValue]) -> list[JsonValue]:
        """Записи пачки с именем обложки только у тех, чьи байты уже можно отдать."""
        has = self.owner.has
        named: list[JsonValue] = []
        for record in results:
            ask = _about(record)
            ready = isinstance(record, dict) and ask is not None and has(_name(ask))
            named.append(
                {**record, FIELD: _name(ask)}
                if ready and ask and isinstance(record, dict)
                else record
            )
        return _ready_posters(serial_parent_posters(named, has), has)

    def arriving(self, results: list[JsonValue]) -> bool:
        """Чья-то обложка из пачки ещё может приехать: в пути или отложена до тишины источника.

        Пустой ответ в минуту 429 откладывает картину до конца тишины (:mod:`hass.hit_claims`),
        и холодный заход, не считая её едущей, закрывал полку заглушками до следующего часа.
        Тишина кончилась - пачка спрашивается снова тем же срочным путём.
        """
        if self.owner.due(results):
            self.owner.offer(results, urgent=True)
        return self.owner.pending(results)


__all__ = ["ShelfPosters"]
