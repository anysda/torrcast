"""Зеркало номера части у :mod:`torrcast.domain.compose`: чью подпись картина несёт.

🔴 TC-859. Счёт номеров у сборки считает по одним номерным именам, и меньшинство имён
вправе назвать картину чужой частью. Отобрать номер у всякого меньшинства нельзя: на этом
же счёте держатся личности картин, и правка в лоб (знаменатель - все раздачи) их ломает.
Здесь поимённо стоят обе стороны цены: картина, у которой номер отобран, и пять картин,
у которых он обязан устоять. Доли раздач тут - настоящие, из замера по ``pools-both.jsonl``.
"""

from torrcast.domain.compose import _compose
from torrcast.domain.release import Release


def _named(title: str, original: str | None = None, season: int | None = None) -> Release:
    return Release(raw_name=title, title=title, original=original, season=season)


def _many(count: int, title: str, original: str | None = None) -> list[Release]:
    return [_named(title, original) for _ in range(count)]


def test_the_picture_a_minority_of_names_called_the_third_gets_no_part_at_all() -> None:
    """«Моб Психо 100» (2016): семь имён из тридцати зовутся «Mob Psycho 100 III».

    Картина несёт первый сезон и говорит об этом сама - её раздачи называют сезон вслух.
    Номера части у неё нет, и стражу спрошенного сезона больше нечего ей предъявить.
    """
    group = _many(7, "Mob Psycho 100 III") + [
        _named("Моб Психо 100", "Mob Psycho 100", season=1) for _ in range(23)
    ]

    assert _compose("tv", 2016, group).part is None


def test_rambo_stays_the_first_part_though_one_name_of_forty_one_says_so() -> None:
    """«Рэмбо: Первая кровь» (1982): часть 1 названа одной раздачей из сорока одной.

    Потеряй она номер - линейка франшизы осталась бы без первой части, и дефолт запроса
    «рэмбо» переехал бы на «Рэмбо: Первая кровь 2» (1985).
    """
    group = [*_many(40, "Рэмбо: Первая кровь", "First Blood"), _named("Рэмбо 1", "First Blood")]

    assert _compose("movie", 1982, group).part == 1


def test_toy_story_three_stays_the_third_part_by_its_original_name() -> None:
    """«История игрушек: Большой побег» (2010): часть 3 названа одной раздачей из двадцати
    девяти, зато её оригинал - «Toy Story 3», а это подпись самой картины.

    Потеряй она номер - запрос «история игрушек 3» остался бы вовсе без дефолта.
    """
    group = [
        *_many(28, "История игрушек: Большой побег", "Toy Story 3"),
        _named("История игрушек 3", "Toy Story 3"),
    ]

    assert _compose("movie", 2010, group).part == 3


def test_the_matrix_reloaded_stays_the_second_part_on_three_names_of_twenty_three() -> None:
    """«Матрица: Перезагрузка» (2003): часть 2 названа тремя раздачами из двадцати трёх."""
    group = _many(20, "Матрица: Перезагрузка", "The Matrix Reloaded") + _many(
        3, "Матрица 2: Перезагрузка", "The Matrix Reloaded"
    )

    assert _compose("movie", 2003, group).part == 2


def test_aliens_stays_the_second_part_on_a_single_name_of_thirty_six() -> None:
    """«Чужие» (1986): часть 2 названа одной раздачей из тридцати шести."""
    group = [*_many(35, "Чужие", "Aliens"), _named("Чужие 2", "Aliens")]

    assert _compose("movie", 1986, group).part == 2


def test_dune_part_two_stays_the_second_part_on_a_single_name_of_one_hundred_nine() -> None:
    """«Дюна: Часть вторая» (2024): часть 2 названа одной раздачей из ста девяти.

    Потеряй она номер - дефолт запроса «дюна» уехал бы с «Дюны» (2021) на «Дюну» (1984).
    """
    group = [
        *_many(108, "Дюна: Часть вторая", "Dune: Part Two"),
        _named("Дюна: Часть 2", "Dune: Part Two"),
    ]

    assert _compose("movie", 2024, group).part == 2


def test_transformers_three_stays_the_third_part_on_eight_names_of_forty() -> None:
    """«Трансформеры 3: Тёмная сторона Луны» (2011): часть 3 названа восемью из сорока.

    Она и есть весь номерной хребет франшизы: без неё линейка рассыпается, и голова
    меню съезжает с «Трансформеров» (2007) на «Трансформеров» (1986) - см. зеркало
    :func:`~torrcast.domain.numbered_line._numbered_line`.
    """
    dark = "Transformers: Dark of the Moon"
    group = [
        *_many(32, "Трансформеры: Тёмная сторона Луны", dark),
        *_many(8, "Трансформеры 3: Тёмная сторона Луны", dark),
    ]

    assert _compose("movie", 2011, group).part == 3
