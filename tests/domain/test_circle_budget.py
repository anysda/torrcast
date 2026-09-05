"""Проверяет потолок ПЕРВОГО круга: он обязан резать хвост и не резать находки."""

from torrcast.domain.circle_budget import FIRST_CIRCLE_TIMEOUT
from torrcast.domain.goal_spare import GOAL
from torrcast.domain.indexer_budget import FRAGILE_TIMEOUT, QUORUM_TIMEOUT, SHORT_TIMEOUT
from torrcast.domain.response_budget import LATE_TIMEOUT


def test_потолок_короче_бюджета_самого_медленного_опорного() -> None:
    """Иначе он украшение: круг ждёт каждого опорного отдельно, и хвост остаётся его."""
    assert FIRST_CIRCLE_TIMEOUT < QUORUM_TIMEOUT


def test_потолок_не_короче_личного_бюджета_ни_одного_источника() -> None:
    """🔴 Тут покупается брак: срезав потолок ниже чьего-то бюджета, мы отнимаем строки
    у того, кто укладывался в СВОЙ срок. Хвост режется ценой находки, а так нельзя.
    """
    assert max(FRAGILE_TIMEOUT, SHORT_TIMEOUT) <= FIRST_CIRCLE_TIMEOUT


def test_потолок_дешевле_цели_но_дороже_ожидания_ответа() -> None:
    """Первый круг не съедает цель целиком, а запрос отставшего живёт дольше потолка -
    иначе опоздавший не опоздал бы, а пропал.
    """
    assert FIRST_CIRCLE_TIMEOUT < GOAL < LATE_TIMEOUT
