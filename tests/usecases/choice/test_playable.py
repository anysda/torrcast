"""Зеркало :mod:`torrcast.usecases.choice.playable`: тупиковая картина уступает тёзке.

🔴 TC-246. Тупик - это картина, у которой после отбора не осталось ни одной раздачи,
годной, живой и не старья разом. Порог живости она проходит честно, и уступает дефолт
ровно ТЁЗКЕ - картине, которую каталог подписал тем же именем.
"""

from __future__ import annotations

from tests.usecases.choice.world import film, plan
from torrcast.usecases.choice import _same_name, playable

#: Живая раздача, которой картину и правда стоит смотреть.
HD = film("Кино 2020 WEB-DL 1080p", seeders=58)
#: Живая по правилам отбора, но старьё: рой её видит, а вечера с нею не будет.
SD = film("Кино 2020 WEB-DLRip 480p", seeders=100, quality="480p")


def test_a_dead_end_picture_yields_the_default_to_its_namesake_with_live_hd() -> None:
    """Замер каталога: «Призраки» приезжают 190 строками, из них 58 HD.

    Дефолтом при этом вставала одноимённая картина с одной SD-раздачей и без нужного
    сезона. То же у «Ангела» (194 / 68), «Убийства» (189 / 91) и «Родины» (128 / 24).
    """
    ghosts = [plan("Призраки", 2019, pool=[SD]), plan("Призраки", 2021, pool=[HD])]

    assert playable(ghosts, [1, 2]) == [2]


def test_a_neighbour_of_the_franchise_is_left_alone_by_this_rule_entirely() -> None:
    """🔴 Соседей по франшизе правило не трогает вовсе, и это ограждение, а не оттенок.

    Дефолт франшизы - первая живая часть, и «Тачки», у которых в каталоге одни
    DVD-образы, обязаны остаться первым пунктом, а не уступить третьей части за её 1080p:
    это другое кино, а не та же вещь под тем же именем.
    """
    cars = [plan("Тачки", 2006, pool=[SD]), plan("Тачки 3", 2017, pool=[HD])]

    assert playable(cars, [1, 2]) == [1, 2]


def test_a_picture_whose_namesakes_are_all_dead_ends_keeps_the_default() -> None:
    """Уступать некому - список остаётся как был, и старьё играется как игралось."""
    junk = [plan("Кино", 1999, pool=[SD]), plan("Кино", 2001, pool=[SD])]

    assert playable(junk, [1, 2]) == [1, 2]


def test_a_picture_with_a_live_hd_release_of_its_own_yields_to_nobody() -> None:
    """⚠️ TC-192 не отменяется: у «Нелюбови» 2017 годная раздача есть, тупиком она не была."""
    unloved = [plan("Нелюбовь", 2017, pool=[HD]), plan("Нелюбовь", 2022, pool=[HD])]

    assert playable(unloved, [1, 2]) == [1, 2]


def test_two_pictures_are_namesakes_whatever_case_the_catalogue_typed_them_in() -> None:
    """Регистр букв каталог пишет как придётся, и тёзку он скрывать не вправе."""
    pair = [plan("НЕЛЮБОВЬ", 2017), plan("Нелюбовь", 2022), plan("Тачки", 2006)]

    assert _same_name(pair, 1, 2) is True
    assert _same_name(pair, 1, 3) is False
