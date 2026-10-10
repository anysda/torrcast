"""Зеркало :mod:`torrcast.domain.parse_release_name`: имя раздачи, разобранное на поля."""

import pytest

from torrcast.domain.cluster import cluster
from torrcast.domain.menu_order import menu_order
from torrcast.domain.parse_release_name import _bare_episode_span, parse_release_name
from torrcast.domain.pick_franchise import pick_franchise


def test_the_whole_name_falls_apart_into_the_fields_the_choice_needs() -> None:
    """Отбор судит раздачу этими полями, а трекер отдаёт их одной строкой."""
    found = parse_release_name("Брат / Brother (1997) BDRip 1080p x264 [Дубляж]")

    assert found.title == "Брат"
    assert found.original == "Brother"
    assert found.year == 1997
    assert found.quality == "1080p"
    assert found.codec == "H.264"
    assert found.source == "BDRip"
    assert found.voices == ("Дубляж",)


def test_a_bare_name_leaves_the_fields_unnamed_instead_of_guessed() -> None:
    """Имя молчит - поле пустое: догадка тут стоила бы зрителю не той картины."""
    found = parse_release_name("Брат")

    assert found.title == "Брат"
    assert found.year is None
    assert found.quality is None
    assert found.codec is None


def test_a_bare_run_of_episodes_is_read_as_a_series() -> None:
    """«1-12» в хвосте длинного латинского имени - это серии, а не номер части."""
    assert _bare_episode_span("The Big Bang Theory 1-12") == tuple(range(1, 13))


def test_a_short_name_with_the_same_tail_is_not_a_run_of_episodes() -> None:
    """У короткого имени «1-2» - это сборник частей, и серий тут не обещано."""
    assert _bare_episode_span("Кино 1-12") == ()


def test_a_collection_is_not_a_series_just_because_its_name_ends_in_e() -> None:
    """🔴 TC-1033. Маркер серии - ОТДЕЛЬНАЯ буква, а не хвост предыдущего слова.

    `Ice Age 1-5` это пять фильмов, и буква `e` перед диапазоном взята из слова `Age`.
    Пока шаблон читал её маркером, человек, спросивший «Ice Age», получал серию
    сериала, которого нет. Номер частей при этом не входит и в имя картины: сборник
    зовётся `Ice Age`, и только под этим именем его узнаёт соседка по выдаче.
    """
    found = parse_release_name("Ice Age 1-5 (2002-2016) BDRip 1080p")

    assert found.kind == "movie"
    assert found.episodes == ()
    assert found.title == "Ice Age", "линейка частей - не часть названия картины"


def test_the_word_episode_stays_a_marker_though_it_ends_in_the_same_letter() -> None:
    """Слово «Episode» кончается на ту же букву и маркером быть обязано.

    Сезона в имени тут нет нарочно: серии обещаны ровно этим словом, и без него
    очередь серий у раздачи опустела бы молча.
    """
    found = parse_release_name("Клиника / Scrubs / Episode 1-12 (2009) HDTV 720p")

    assert found.episodes == tuple(range(1, 13))
    assert found.kind == "tv"


@pytest.mark.parametrize(
    "name",
    [
        "Брат и Брат 2 (1997, 2000) WEB-DL 1080p [Дилогия]",
        "Брат и Брат 2 | Дилогия (1997-2000) BDRip 720p",
        "Матрица (Трилогия) BDRip 1080p",
    ],
)
def test_a_film_count_label_anywhere_in_the_name_marks_a_collection(name: str) -> None:
    """Метка «[Дилогия]» после года называет пачку фильмов так же, как «Дилогия» до него.

    Сборник «Брат и Брат 2» с такой меткой в хвосте не узнавался и вставал в меню «Брат»
    первым пунктом: без меню играл он, а внутри - крупнейший файл, то есть «Брат 2».
    """
    assert parse_release_name(name).collection is True


@pytest.mark.parametrize(
    "name",
    [
        "Брат / Brat (1997) BDRip 1080p",
        "Трилогия смерти (2010) WEB-DL 1080p",
        "Властелин колец трилогия часть 1 (2001) BDRip",
    ],
)
def test_the_label_word_inside_a_title_is_not_a_collection(name: str) -> None:
    """Слово в самом названии - не метка: метка стоит отдельно, в скобках или за чертой."""
    assert parse_release_name(name).collection is False


def test_brat_is_the_first_line_of_its_own_menu() -> None:
    """Спросили «Брат» - первым пунктом стоит «Брат» 1997 года, а не дилогия и не «Брат 2»."""
    names = [
        "Брат и Брат 2 (1997, 2000) WEB-DL 1080p [Дилогия]",
        "Брат и Брат 2 | Дилогия (1997-2000) BDRip 720p",
        "Брат / Brat (1997) BDRip 1080p [Дубляж]",
        "Брат 2 (2000) BDRip 1080p",
        "Брат и сестра (2022) WEB-DL 1080p",  # с ней меню строится по франшизе «Брат»
        "Решала: Брат (2022) WEB-DL 1080p",
    ]
    pictures = cluster([parse_release_name(name) for name in names])

    assert [(p.title, p.year) for p in menu_order(pick_franchise("брат", pictures))][:2] == [
        ("Брат", 1997),
        ("Брат 2", 2000),
    ]


def test_a_year_glued_to_the_bracket_of_the_original_is_still_the_year() -> None:
    """«Брат(Brat)1997 [1080P]» - это «Брат» 1997 года, а не картина «Брат 1997» без года.

    Год без пробела за скобкой не читался, и в меню по «Брат 1997» вставала отдельная
    безгодовая «Брат 1997 (?)», а страж «имя названо целиком» брал именно её.
    """
    names = ["Брат(Brat)1997 [1080P]", "Брат(Brat)1997", "Брат / Brat (1997) BDRip 1080p"]
    pictures = cluster([parse_release_name(name) for name in names])

    assert [(p.title, p.year, len(p.releases)) for p in pictures] == [("Брат", 1997, 3)]
