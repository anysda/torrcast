"""Срок жизни запроса к индексеру после того, как круг перестал его ждать."""

from __future__ import annotations

from typing import Final

from torrcast.domain.indexer_budget import indexer_budget
from torrcast.domain.quorum_indexer import quorum_indexer

#: Срок жизни фонового HTTP-запроса к кворумному индексеру. Он не держит круг:
#: :data:`~torrcast.domain.indexer_budget.QUORUM_TIMEOUT` по-прежнему выпускает меню. Но
#: медленный честный ответ должен успеть доехать доливом: сохранённый замер на 170
#: запросах дал ответы Knaben на 31.73 и 32.72 с, причём второй принёс 66 строк. 45 секунд
#: оставляют им запас и заканчивают запрос раньше внутреннего потолка Prowlarr.
LATE_TIMEOUT: Final = 45.0


def response_budget(name: str) -> float:
    """Сколько живёт HTTP-запрос после того, как круг перестал его ждать.

    Потолок следующего круга сюда не входит: он ограничивает путь до меню, а не
    уничтожает ответ. Некворумные сохраняют свой личный срок; лишь кворумный может
    честно ответить позднее срока круга, и такой ответ забирает долив.
    """
    budget = indexer_budget(name)
    return max(budget, LATE_TIMEOUT) if quorum_indexer(name) else budget


__all__ = ["LATE_TIMEOUT", "response_budget"]
