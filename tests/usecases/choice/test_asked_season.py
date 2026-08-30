"""Зеркало :mod:`torrcast.usecases.choice.asked_season`: сезон, названный самим запросом.

Номер части у сериала и есть номер сезона: тем же прочтением запрос «имя N» становится
«имя sNe1». Значит картина, подписанная каталогом частью 2, первого сезона не несёт, и
дефолт спрошенного первого сезона ей не положен. Замер по сохранённым выдачам: «код гиас
s1e1» ставил дефолтом «Код Гиас: Восставший Лелуш 2» (2008) при живом первом сезоне в том
же меню.
"""

from __future__ import annotations

from dataclasses import replace

from tests.usecases.choice.world import film, plan
from torrcast.domain.compose import _compose
from torrcast.domain.release import Release
from torrcast.usecases.choice.asked_season import asked_season


def test_a_named_season_leaves_out_the_picture_the_catalogue_numbered_otherwise() -> None:
    """Спросили первый сезон - вторая часть франшизы дефолта не берёт."""
    geass = [
        plan("Код Гиас: Восставший Лелуш 2", 2008, kind="tv", part=2, season=1, asked_series=True),
        plan("Код Гиас: Восставший Лелуш", 2006, kind="tv", season=1, asked_series=True),
    ]

    assert asked_season(geass, [1, 2]) == [2]


def test_a_query_that_named_no_episode_lets_every_part_stay_in_the_running() -> None:
    """Серии не спрашивали - номер сезона не назван, и судить картины по нему нечем.

    Запрос «код гиас» - это просьба про франшизу целиком, и там дефолт решают живость и
    хронология, а не цифра в названии части.
    """
    geass = [
        plan("Код Гиас: Восставший Лелуш 2", 2008, kind="tv", part=2, season=1),
        plan("Код Гиас: Восставший Лелуш", 2006, kind="tv", season=1),
    ]

    assert asked_season(geass, [1, 2]) == [1, 2]


def test_a_menu_without_a_single_picture_of_the_asked_season_counts_as_it_counted() -> None:
    """Подходящих не осталось ни одной - считаем как считали.

    Спрошенного сезона в меню нет вовсе, и пустой ответ вместо картины был бы хуже
    неточного номера: цифре в скобках стало бы не на что указывать.
    """
    geass = [
        plan("Код Гиас: Восставший Лелуш 2", 2008, kind="tv", part=2, season=1, asked_series=True),
        plan("Код Гиас: Восставший Лелуш 3", 2010, kind="tv", part=3, season=1, asked_series=True),
    ]

    assert asked_season(geass, [1, 2]) == [1, 2]


def test_a_picture_numbered_by_a_minority_still_carries_the_season_its_names_call() -> None:
    """🔴 TC-856. Номер части у картины бывает от меньшинства её же имён.

    «Моб Психо 100» (2016) несёт все три сезона, но семь её раздач из тридцати зовутся
    «Mob Psycho 100 III», и счёт номеров подписывает картину частью 3. По номерам тогда
    не проходит НИКТО, прежний отвод возвращал всё меню разом - и дефолт первого сезона
    садился на соседнюю часть. Ступень имён спасает ровно этот случай: сезон, названный
    раздачей вслух, картина точно несёт.
    """
    psycho = [
        plan("Mob Psycho 100 2", None, kind="tv", part=2, season=1, asked_series=True),
        plan(
            "Моб Психо 100",
            2016,
            kind="tv",
            part=3,
            season=1,
            asked_series=True,
            pool=[replace(film("Моб Психо 100 [S01] (2016) BDRip", kind="tv"), season=1)],
        ),
    ]

    assert asked_season(psycho, [1, 2]) == [2]


def test_a_picture_that_named_no_season_at_all_does_not_pass_by_names() -> None:
    """Отрицательная проба ступени имён: молчание сезоном не считается.

    Обе картины подписаны чужими частями и о сезонах молчат - значит имена не сказали
    ничего, и ступень обязана пропустить ход, оставив прежний ответ «считаем как
    считали». Пройди тут молчание - ступень отбирала бы картины наугад.
    """
    psycho = [
        plan("Mob Psycho 100 2", None, kind="tv", part=2, season=1, asked_series=True),
        plan("Mob Psycho 100 3", None, kind="tv", part=3, season=1, asked_series=True),
    ]

    assert asked_season(psycho, [1, 2]) == [1, 2]


def test_the_first_season_passes_the_narrow_gate_the_minority_number_used_to_shut() -> None:
    """🔴 TC-859. Тот же случай, но корнем: у картины больше нет чужого номера части.

    Ступень имён (TC-856) закрыла симптом - подмену сезона, а меню всё равно приезжало
    целиком: по номерам не проходил НИКТО, и узкие ворота отступали к «считаем как
    считали». Теперь семь имён из тридцати картину частью не подписывают
    (:func:`~torrcast.domain.part_of_picture.part_of_picture`), и первый сезон проходит
    ПЕРВОЙ ступенью - той, где сезон и решается, а не последней уступкой.
    """
    group = [Release(raw_name="Mob Psycho 100 III", title="Mob Psycho 100 III") for _ in range(7)]
    group += [
        Release(
            raw_name="Моб Психо 100", title="Моб Психо 100", original="Mob Psycho 100", season=1
        )
        for _ in range(23)
    ]
    psycho = [
        plan("Моб Психо 100", 2018, kind="tv", part=2, season=1, asked_series=True),
        plan(
            "Моб Психо 100",
            2016,
            kind="tv",
            part=_compose("tv", 2016, group).part,
            season=1,
            asked_series=True,
        ),
    ]

    assert asked_season(psycho, [1, 2]) == [2]
