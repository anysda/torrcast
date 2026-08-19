"""Проверяет список опорных источников: их круг дожидается до показа списка."""

from torrcast.domain.quorum_indexer import quorum_indexer
from torrcast.domain.wait_indexer import wait_indexer


def test_опорных_ждём() -> None:
    """Кворумного - потому что без него каталога нет, RuTor - ради русской озвучки."""
    assert wait_indexer("Knaben")
    assert wait_indexer("RuTor")


def test_русскую_озвучку_ждём_и_у_сменщика_rutor() -> None:
    """JacRed несёт тот же русский пул: без ожидания его строки приезжают после выбора."""
    assert wait_indexer("JacRed")
    assert wait_indexer("jacred")


def test_остальных_круг_не_ждёт() -> None:
    """Некворумные доезжают доливом: их молчание не вправе держать меню (TC-118)."""
    assert not wait_indexer("Nyaa.si")
    assert not wait_indexer("YTS")


def test_кворумный_всегда_опорный() -> None:
    """Обратное неверно: опорным быть можно и без права судить о полноте каталога."""
    assert wait_indexer("Knaben") and quorum_indexer("Knaben")
    assert wait_indexer("RuTor") and not quorum_indexer("RuTor")
    assert wait_indexer("JacRed") and not quorum_indexer("JacRed")
