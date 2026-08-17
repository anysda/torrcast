"""Проверяет, кого считаем упёршимся в потолок страницы выдачи."""

from torrcast.domain.capped_indexers import INDEXER_PAGE, capped_indexers


def test_полная_страница_это_обрезанный_хвост() -> None:
    assert capped_indexers({"Knaben": INDEXER_PAGE, "RuTor": 7}) == ("Knaben",)


def test_потолок_не_следует_за_клиентским_лимитом() -> None:
    """Параметр ``limit`` потолка не меняет: запросы на 100 и 200 дают ту же сотню."""
    assert capped_indexers({"Knaben": INDEXER_PAGE, "RuTor": INDEXER_PAGE + 5}) == (
        "Knaben",
        "RuTor",
    )


def test_неполная_выдача_потолком_не_считается() -> None:
    assert capped_indexers({"Knaben": INDEXER_PAGE - 1, "RuTor": 0}) == ()
    assert capped_indexers({}) == ()
