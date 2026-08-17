"""Совместимый фасад связи номера из ``cast releases`` с показанной раздачей.

Разбор магнита живёт в :mod:`torrcast.domain.info_hash`, файл с порядком таблицы - в
:class:`~torrcast.adapters.filesystem.release_pins.ReleasePins`.
"""

from torrcast.adapters.filesystem.release_pins import pins
from torrcast.domain.info_hash import info_hash

__all__ = ["info_hash", "recalled", "remember"]

#: Атомарно запомнить порядок последней таблицы этого запроса.
remember = pins.remember
#: Вернуть хэш, стоявший под номером в последней показанной таблице.
recalled = pins.recalled
