"""Зеркало :mod:`torrcast.usecases.choice.named_take`: что берёт сработавший страж имени.

🔴 TC-812: страж «имя названо целиком» (TC-715) на обычном пути больше не спрашивает -
он берёт живейшую: из живых названных, а если живой названной нет - из картин
названного типа.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, outside, parts, plan
from torrcast.usecases.choice.named_take import named_take


def test_a_dead_named_picture_yields_to_the_liveliest_of_the_asked_kind() -> None:
    """«блич s1e1»: у названного «Блича» 2004 рой ниже порога - взята живая тёзка 2022."""
    bleach = [
        plan("Блич", 2004, kind="tv", seeders=3, asked_series=True),
        plan("Блич: Тысячелетняя кровавая война", 2022, kind="tv", seeders=40, asked_series=True),
    ]

    with outside(Outside()):
        assert named_take(bleach, "блич") == 2


def test_a_living_named_picture_is_the_liveliest_of_the_named() -> None:
    """«чернобыль s1e5»: названные живы - берётся живейшая ИЗ НИХ, а не соседка по меню.

    Уйти на «Зону отчуждения», которой человек не называл, - та самая подмена, ради
    которой страж и стоит, хоть её рой и жив.
    """
    chernobyl = [
        plan("Чернобыль: Последнее предупреждение", 1991, seeders=10, asked_series=True),
        plan("Чернобыль. Зона отчуждения", 2014, kind="tv", seeders=60, asked_series=True),
        plan("Чернобыль", 2019, kind="tv", seeders=79, asked_series=True),
        plan("Чернобыль", 2022, kind="tv", seeders=50, asked_series=True),
    ]

    with outside(Outside()):
        assert named_take(chernobyl, "чернобыль") == 3


def test_a_silent_guard_means_no_take() -> None:
    """Дефолт и есть целиком названная картина - страж молчит, и брать тут нечего."""
    mummy = parts(("Мумия", 1999, 58), ("Мумия", 2017, 47))

    with outside(Outside()):
        assert named_take(mummy, "мумия") == 0


def test_a_numbered_franchise_is_not_this_guard() -> None:
    """«рэмбо» - территория франшизы: там дефолт - первая живая часть, и страж молчит."""
    rambo = [
        plan("Рэмбо: Первая кровь", 1982, part=1, seeders=74),
        plan("Рэмбо 2", 1985, part=2, seeders=50),
        plan("РэмбО", 2022, kind="tv", seeders=2),
    ]

    with outside(Outside()):
        assert named_take(rambo, "рэмбо") == 0
