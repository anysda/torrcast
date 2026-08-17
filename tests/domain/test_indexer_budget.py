"""Проверяет личные бюджеты индексеров: роль в круге и короткий список."""

from torrcast.domain.goal_spare import GOAL
from torrcast.domain.indexer_budget import (
    EXTRA_TIMEOUT,
    FRAGILE_TIMEOUT,
    QUORUM_TIMEOUT,
    SHORT_TIMEOUT,
    indexer_budget,
)


def test_кворумного_ждём_дольше_остальных() -> None:
    """🔴 TC-226. Хвост поиска - это Knaben: 502 через 10-15 с плюс ретрай Prowlarr.
    Резать его личным бюджетом в 3-5 с нельзя - он несёт 41% каталога, и замер дал
    1 подмену дефолта и 7 подмен верхнего релиза на 100 запросов."""
    assert indexer_budget("Knaben") == QUORUM_TIMEOUT == 20.0


def test_короткий_список_бюджет_только_урезает() -> None:
    """🔴 TC-213: у YTS терять нечего (+2.1% к пулу, ноль уникальных дыр), а платили мы
    за него полным бюджетом - залипший ответ выбирал все 20 с."""
    assert indexer_budget("YTS") == SHORT_TIMEOUT == 6.0
    assert SHORT_TIMEOUT < EXTRA_TIMEOUT, "короткий бюджет обязан быть заметно короче"


def test_хрупкие_источники_молчат_три_секунды() -> None:
    """TC-498: один аниме-источник не вправе съесть всю цель продукта."""
    assert indexer_budget("Nyaa.si") == FRAGILE_TIMEOUT == 3.0
    assert indexer_budget("RuTor") == 3.0
    assert FRAGILE_TIMEOUT < GOAL / 2


def test_некворумный_ждёт_столько_сколько_его_выдаче_есть_куда_лечь() -> None:
    """Круг их не ждёт, поэтому бюджет отмеряется целью, а не путём до меню."""
    assert indexer_budget("SomeOther") == EXTRA_TIMEOUT == GOAL


def test_имя_судим_подстрокой_в_любом_регистре() -> None:
    """Номер у индексера свой на каждой установке, поэтому судим по имени."""
    assert indexer_budget("yts.mx") == SHORT_TIMEOUT
    assert indexer_budget("KNABEN") == QUORUM_TIMEOUT
