"""Проверяет, кто идёт первым кругом, а кто ждёт фолбэка (TC-229)."""

from torrcast.domain.circle_indexers import circle_indexers

_ALL = ((1, "Knaben"), (2, "RuTor"), (3, "Nyaa.si"))


def test_не_аниме_запрос_оставляет_анимешных_фолбэку() -> None:
    """Nyaa молчит на 79% таких запросов, а параллель по нему грозит 504-баном на часы."""
    first, later = circle_indexers(_ALL, "матрица")
    assert first == ((1, "Knaben"), (2, "RuTor"))
    assert later == ((3, "Nyaa.si"),)


def test_аниме_запрос_зовёт_анимешных_сразу() -> None:
    first, later = circle_indexers(_ALL, "Naruto [TV]")
    assert first == _ALL
    assert later == ()


def test_без_обычных_индексеров_круг_идёт_анимешными() -> None:
    """Иначе первый круг вышел бы пустым, а спрашивать было бы кого."""
    first, later = circle_indexers(((3, "Nyaa.si"),), "матрица")
    assert first == ((3, "Nyaa.si"),)
    assert later == ()


def test_без_анимешных_откладывать_нечего() -> None:
    first, later = circle_indexers(((1, "Knaben"),), "матрица")
    assert first == ((1, "Knaben"),)
    assert later == ()


def test_порядок_индексеров_сохраняется() -> None:
    """Круг спрашивает в порядке списка Prowlarr, и раскладка его не перемешивает."""
    first, _later = circle_indexers(((2, "RuTor"), (1, "Knaben")), "матрица")
    assert first == ((2, "RuTor"), (1, "Knaben"))
