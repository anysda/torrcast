"""Завод кодировщика тяжёлых кусков.

Кладёт его композиционный корень (:mod:`torrcast.runtime.wire`) под именем ``Recoder``.

⚠️ Доводы завода тут не перечислены, и это не небрежность: сетку показ отдаёт заводу
своим договором (:class:`MediaGrid`), а настоящий кодировщик объявляет её СВОИМ, более
узким классом адаптера. Назвать доводы значило бы пообещать заводу больше, чем он умеет,
и тайпчек честно на это жалуется. Названо то, что показ отсюда получает и чем потом
пользуется, - сам кодировщик; доводы вызова сверяет адаптер на своей стороне.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

from torrcast.ports.recode.spot_recoder import SpotRecoder

#: Чем показ заводит кодировщик тяжёлых кусков.
SpotRecoders: TypeAlias = Callable[..., SpotRecoder]
