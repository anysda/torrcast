"""Проверяет срок жизни запроса после того, как круг перестал его ждать."""

from torrcast.domain.indexer_budget import indexer_budget
from torrcast.domain.response_budget import LATE_TIMEOUT, response_budget


def test_ответ_кворумного_живёт_дольше_круга() -> None:
    """TC-454: бюджет круга выпускает меню, но честный поздний ответ не обрывает.
    Сохранённый замер на 170 запросах дал ответы на 31.73 и 32.72 с, причём второй
    принёс 66 строк."""
    assert response_budget("Knaben") == LATE_TIMEOUT == 45.0
    assert response_budget("Knaben") > indexer_budget("Knaben")


def test_некворумный_сохраняет_свой_личный_срок() -> None:
    """Его выдаче ложиться уже некуда: показ ушёл, и долив ей ничего не покупает."""
    assert response_budget("Nyaa.si") == indexer_budget("Nyaa.si")
    assert response_budget("YTS") == indexer_budget("YTS")
