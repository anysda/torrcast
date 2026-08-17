"""Проверяет отсечку «пул почти пуст», после которой зовём анимешные индексеры."""

from torrcast.domain.anime_fallback import FALLBACK_POOL, anime_fallback


def test_тощий_пул_зовёт_фолбэк() -> None:
    assert anime_fallback(FALLBACK_POOL - 1, answered=True)
    assert anime_fallback(0, answered=True), "пустая выдача ответивших - самый тощий пул"


def test_полный_пул_фолбэка_не_требует() -> None:
    """Лишний круг по Nyaa - лишний риск 504-бана Prowlarr на часы."""
    assert not anime_fallback(FALLBACK_POOL, answered=True)
    assert not anime_fallback(50, answered=True)


def test_молчание_круга_фолбэком_не_лечится() -> None:
    """Не ответил никто - это не тощий пул, а отказ, и лишний круг тут ни при чём."""
    assert not anime_fallback(0, answered=False)
