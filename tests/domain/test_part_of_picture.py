"""Зеркало :mod:`torrcast.domain.part_of_picture`: чей номер части - картины или раздачи.

Счёт номеров даёт лишь претендента, и меньшинство имён вправе назвать картину чужой
частью. Отбирается номер только тогда, когда против него сошлись все три свидетеля разом:
имя самой картины, доля среди ВСЕХ её раздач и сезоны, которые её раздачи называют вслух.
За номер довольно любого одного.
"""

from torrcast.domain.part_of_picture import part_of_picture
from torrcast.domain.release import Release


def _named(title: str, season: int | None = None) -> Release:
    return Release(raw_name=title, title=title, season=season)


def _psycho(numbered: int = 7, whole: int = 30) -> list[Release]:
    """Раздачи «Моб Психо 100» (2016) той же долей, что в замере: семь имён из тридцати."""
    return [_named("Mob Psycho 100 III") for _ in range(numbered)] + [
        _named("Моб Психо 100", season=1) for _ in range(whole - numbered)
    ]


def test_the_number_a_minority_calls_against_the_seasons_of_the_picture_is_not_hers() -> None:
    """🔴 TC-859. Все три свидетеля против: имя молчит, доля мала, сезоны зовут другое."""
    assert part_of_picture(3, "Моб Психо 100", "Mob Psycho 100", _psycho()) is None


def test_the_number_the_picture_carries_in_her_own_name_stays_hers() -> None:
    """Имя картины - подпись самой картины: против неё двое других свидетелей не в счёт."""
    assert part_of_picture(3, "Моб Психо 100 III", None, _psycho()) == 3


def test_the_number_the_original_name_of_the_picture_carries_stays_hers() -> None:
    """Оригинал выбран тем же большинством, что и название: это тоже подпись картины."""
    assert part_of_picture(3, "Моб Психо 100", "Mob Psycho 100 III", _psycho()) == 3


def test_the_number_most_of_the_whole_group_calls_stays_hers() -> None:
    """Знаменатель тут все раздачи: большинство ВСЕХ имён - это уже голос картины."""
    assert part_of_picture(3, "Моб Психо 100", None, _psycho(numbered=16)) == 3


def test_the_number_the_seasons_of_the_picture_confirm_stays_hers() -> None:
    """Сезоны картины называют спорный номер - меньшинство имён сказало правду."""
    group = [_named("Моб Психо 100 II")] + [_named("Моб Психо 100", season=2) for _ in range(36)]

    assert part_of_picture(2, "Моб Психо 100", "Mob Psycho 100", group) == 2


def test_a_picture_whose_releases_kept_silent_about_seasons_keeps_any_number() -> None:
    """Молчание доводом не считается: третий свидетель у фильма не говорит никогда.

    Ровно на этом держатся личности картин - «Матрица: Перезагрузка» зовётся второй
    частью тремя раздачами из двадцати трёх, и большинства у неё не будет никогда.
    """
    group = [_named("Матрица 2: Перезагрузка") for _ in range(3)] + [
        _named("Матрица: Перезагрузка") for _ in range(20)
    ]

    assert part_of_picture(2, "Матрица: Перезагрузка", "The Matrix Reloaded", group) == 2


def test_a_picture_without_a_counted_number_gets_none() -> None:
    """Претендента нет - решать нечего, и выдумывать номер правило не берётся."""
    assert part_of_picture(None, "Моб Психо 100", "Mob Psycho 100", _psycho()) is None
