"""Гейт подмены: та же ли картина возглавляет выдачу после добора."""

from __future__ import annotations

from torrcast.domain.facts.origin import Origin
from torrcast.domain.picture import Picture
from torrcast.usecases.reinforce.same_picture import same_picture

_ASCENT = Picture(title="Восхождение", year=1976, original="The Ascent")
_CLIMBERS = Picture(title="Восхождение", year=2019, original="The Climbers")


def test_the_passport_year_has_the_last_word() -> None:
    """Справка отвечает про спрошенную картину: другой год - приехал однофамилец."""
    assert same_picture(_ASCENT, _ASCENT, Origin(year=1976), proven=False)
    assert not same_picture(_ASCENT, _CLIMBERS, Origin(year=1976), proven=True)


def test_a_year_apart_is_the_release_year_not_a_swap() -> None:
    """Год производства против года проката: раздачи путают их постоянно."""
    later = Picture(title="Восхождение", year=1977, original="The Ascent")

    assert same_picture(_ASCENT, later, Origin(year=1976), proven=False)


def test_the_same_original_is_the_same_picture_across_years() -> None:
    """Ремейк с тем же оригиналом - добор, а не подмена: справка знает 2006, каталог 2019."""
    old = Picture(title="Корзинка фруктов", year=2006, original="Fruits Basket")
    remake = Picture(title="Корзинка фруктов", year=2019, original="Fruits Basket")

    assert same_picture(old, remake, Origin(title="Fruits Basket", year=2006), proven=True)


def test_into_the_void_only_a_proven_name_is_believed() -> None:
    """Русский запрос не нашёл ничего - сверять не с чем, и решает происхождение имени."""
    assert same_picture(None, _CLIMBERS, Origin(), proven=True)
    assert not same_picture(None, _CLIMBERS, Origin(), proven=False), "наугад взятому веры нет"


def test_nothing_came_is_never_the_same_picture() -> None:
    """После добора не осталось никого - подтверждать нечего."""
    assert not same_picture(_ASCENT, None, Origin(year=1976), proven=True)


def test_without_any_year_the_franchise_answers() -> None:
    """Сериалы часто без года: подмену франшиза не ловит, но и врать не будет."""
    ours = Picture(title="Ангел", year=None, kind="tv")
    same = Picture(title="Ангел 2", year=None, kind="tv")
    alien = Picture(title="Клиника", year=None, kind="tv")

    assert same_picture(ours, same, Origin(), proven=False)
    assert not same_picture(ours, alien, Origin(), proven=False)
