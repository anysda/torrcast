"""Несёт ли картина спрошенный сезон - номером части или именем раздачи."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.seasons_named import seasons_named

if TYPE_CHECKING:
    from torrcast.domain.picture import Picture


def carries_season(picture: Picture, season: int) -> bool:
    """Несёт ли картина спрошенный сезон - номером части или именем раздачи.

    🔴 TC-860. Тем же вопросом спрашивает и честная строка выбора
    (:func:`~torrcast.usecases.choice.default_note.default_note`): дефолт мог сесть на
    картину, чья часть спрошенному сезону не отвечает, ровно ТОГДА, когда узкие ворота
    :func:`~torrcast.usecases.choice.asked_season.asked_season` не нашли никого и
    отступили к «считаем как считали» - и картина без части не участвует в этой
    развилке вовсе, её часть безусловна.
    """
    return picture.part is None or picture.part == season or season in seasons_named(picture)
