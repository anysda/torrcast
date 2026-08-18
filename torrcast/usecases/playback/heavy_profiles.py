"""Завод профиля тяжести: карта опорных кадров плюс сетка дают вес каждого куска.

Кладёт его композиционный корень (:mod:`torrcast.runtime.wire`) под именем ``Weights``.

⚠️ Доводы завода тут не перечислены, и это не небрежность: сетку показ называет своим
широким договором (:class:`MediaGrid`), а настоящий счётчик объявляет её СВОИМ, более
узким классом адаптера. Перечислить доводы значило бы пообещать заводу больше, чем он
умеет, и тайпчек честно на это жалуется. Названо то, что показ отсюда получает и чем
потом решает, нужен ли кодировщик тяжёлых кусков вовсе.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

from torrcast.usecases.playback.heavy_profile import HeavyProfile

#: Чем показ строит профиль тяжести: карта, сетка и поправка «контейнер → ТВ».
HeavyProfileOf: TypeAlias = Callable[..., HeavyProfile | None]
