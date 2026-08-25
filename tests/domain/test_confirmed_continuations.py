"""Зеркало :mod:`torrcast.domain.confirmed_continuations`: что дописывается к франшизе."""

from torrcast.domain.confirmed_continuations import confirmed_continuations
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(title: str, year: int, original: str | None, copies: int = 1) -> Picture:
    releases = [Release(raw_name=title, title=title) for _ in range(copies)]
    return Picture(title=title, year=year, original=original, releases=releases)


BASE = [_picture("Матрица", 1999, "The Matrix", copies=9)]


def test_a_part_whose_original_name_shares_the_root_is_added() -> None:
    """Продолжение подтверждается латинским именем: русское название расходится всегда."""
    later = [_picture("Матрица: Перезагрузка", 2003, "The Matrix: Reloaded")]
    groups = {"матрица": BASE, "матрица-перезагрузка": later}

    found = confirmed_continuations(groups, "матрица", BASE)

    assert [p.title for p in found] == ["Матрица: Перезагрузка"]


def test_a_namesake_from_another_franchise_is_not_added() -> None:
    """Имя начинается так же, а корень оригинала другой - это чужая картина."""
    stranger = [_picture("Матрица времени", 2017, "ARQ")]
    groups = {"матрица": BASE, "матрица-времени": stranger}

    assert confirmed_continuations(groups, "матрица", BASE) == []


def test_a_part_older_than_the_franchise_itself_is_not_a_continuation() -> None:
    """Продолжение позже начала: вышедшее раньше первой части ею не продолжается."""
    earlier = [_picture("Аниматрица", 1995, "The Matrix: Animatrix")]
    groups = {"матрица": BASE, "матрица-аниматрица": earlier}

    assert confirmed_continuations(groups, "матрица", BASE) == []


def test_a_franchise_without_a_single_original_name_confirms_nothing() -> None:
    """Подтверждать нечем: без латинского корня добор был бы догадкой по началу имени."""
    base = [_picture("Матрица", 1999, None)]
    later = [_picture("Матрица: Перезагрузка", 2003, "The Matrix: Reloaded")]

    assert (
        confirmed_continuations({"матрица": base, "матрица-перезагрузка": later}, "матрица", base)
        == []
    )
