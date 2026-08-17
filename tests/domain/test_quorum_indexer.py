"""Проверяет, кого считаем кворумом: без него пустая выдача ничего не доказывает."""

from torrcast.domain.quorum_indexer import QUORUM_INDEXERS, quorum_indexer


def test_кворумного_узнаём_по_подстроке_в_любом_регистре() -> None:
    """Имя приходит от Prowlarr как есть, поэтому сверяем подстрокой, а не равенством."""
    assert quorum_indexer("Knaben")
    assert quorum_indexer("knaben.org")
    assert quorum_indexer("KNABEN")


def test_остальные_источники_кворумом_не_считаются() -> None:
    """RuTor каталог сужает, но не убивает поиск: сменный источник у озвучки есть."""
    assert not quorum_indexer("RuTor")
    assert not quorum_indexer("Nyaa.si")
    assert not quorum_indexer("YTS")


def test_кворум_не_пуст() -> None:
    """Пустой кворум означал бы, что честной пустой выдачи не бывает вовсе."""
    assert QUORUM_INDEXERS
