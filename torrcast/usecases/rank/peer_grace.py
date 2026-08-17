"""Сколько раздаче даётся на первый контакт роя; зовёт отбраковка на стенде."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

from torrcast.domain.rank_settings import FULL_HEIGHT, PEER_GRACE, STEP_GRACE

if TYPE_CHECKING:
    _Plan: TypeAlias = Any


def peer_grace(plan: _Plan, number: int, queue: list[int]) -> float:
    """Сколько этой раздаче даётся на ПЕРВЫЙ КОНТАКТ роя, секунды.

    🔴 TC-387. Отсрочка назначается ценой ошибки, а не свойствами раздачи. Обычная
    (:data:`PEER_GRACE`) стоит одного места в очереди: молчаливый релиз пропускается, а
    следующий спрашивается всё равно. Но когда следующий ступенью ниже, ошибка стоит
    обещанной чёткости - живой 1080p уступает 720p не своим роем, а нашим нетерпением, -
    и такой раздаче даётся :data:`STEP_GRACE`.

    Ступень тут решается ИМЕНАМИ соседей, а не сидами: живость раздачи в эту минуту как
    раз и есть то, чего мы ещё не знаем. Молчащее о разрешении имя стоит с низкими:
    подтвердить его нечем, пока раздачу не подняли, и ровно так же его судит
    :func:`is_full_hd`.

    Соседи берутся из фактического хвоста ``queue`` после этой раздачи. Поэтому ручной
    выбор, проверка по звуку и уже пройденный сосед отсрочку не удлиняют. Ворота и
    нужная серия учтены при построении самой очереди (:meth:`_Plan.candidates`).
    """
    release = plan.ranked[number - 1]
    if release.height < FULL_HEIGHT or number not in queue:
        return PEER_GRACE
    after = queue[queue.index(number) + 1 :]
    lower = any(plan.ranked[other - 1].height < FULL_HEIGHT for other in after)
    return STEP_GRACE if lower else PEER_GRACE
