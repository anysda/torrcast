"""Зеркало :mod:`torrcast.domain.pick_franchise`: какие картины отвечают запросу."""

from torrcast.domain.cluster import cluster
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release

_NAMES = [
    "Тачки: Байки Мэтра / Cars Toon: Mater's Tall Tales (2008) BDRip 1080p",
    "Тачки: Байки Мэтра / Cars Toon: Mater's Tall Tales (2010) BDRip 1080p",
    "Тачки / Cars (2006) BDRip 1080p",
    "Тачки 2 / Cars 2 (2011) BDRip 1080p",
]


def _pictures() -> list[Picture]:
    return cluster([parse_release_name(name) for name in _NAMES])


def _picture(
    title: str,
    year: int,
    original: str | None = None,
    part: int | None = None,
    aliases: tuple[str, ...] = (),
) -> Picture:
    return Picture(
        title=title,
        year=year,
        original=original,
        part=part,
        aliases=aliases,
        releases=[Release(raw_name=title, title=title)],
    )


FIRST = _picture("Брат", 1997, "Brother")
SECOND = _picture("Брат 2", 2000, "Brother 2", part=2)
STRANGER = _picture("Сестра", 2019, "Sister")
POOL = [FIRST, SECOND, STRANGER]


def test_a_subtitle_names_its_own_pictures() -> None:
    """Так работает запрос, который в карточке отвечает четырьмя картинами."""
    found = pick_franchise("Байки Мэтра", _pictures())

    assert [(p.title, p.year) for p in found] == [
        ("Тачки: Байки Мэтра", 2008),
        ("Тачки: Байки Мэтра", 2010),
    ]


def test_one_missing_letter_is_not_a_missing_picture() -> None:
    """🔴 TC-777. «Байки Мэтр» отказывал там, где «Байки Мэтра» давало картины."""
    assert [p.year for p in pick_franchise("Байки Мэтр", _pictures())] == [2008, 2010]


def test_the_year_from_our_own_menu_is_taken_back() -> None:
    """🔴 TC-777. Год мы печатаем сами - «(2008)», - и он обязан сужать, а не отказывать."""
    assert [p.year for p in pick_franchise("Байки Мэтра 2008", _pictures())] == [2008]


def test_a_year_nobody_has_leaves_the_pictures_of_the_name() -> None:
    """Год ошибиться может, а имя названо верно - отказывать по одному году не за что."""
    assert [p.year for p in pick_franchise("Байки Мэтра 1999", _pictures())] == [2008, 2010]


def test_a_name_the_catalogue_does_not_know_is_still_nothing() -> None:
    assert pick_franchise("хоббит", _pictures()) == []


def test_the_franchise_name_brings_the_whole_franchise_in_order() -> None:
    """Спросили франшизу - в меню идут все её части, и первая стоит первой."""
    assert [p.title for p in pick_franchise("Брат", POOL)] == ["Брат", "Брат 2"]


def test_a_number_in_the_query_names_one_part() -> None:
    """«Брат 2» - это одна картина: показывать после номера меню было бы лишним."""
    assert [p.title for p in pick_franchise("Брат 2", POOL)] == ["Брат 2"]


def test_the_original_name_leads_to_the_same_franchise() -> None:
    """Картину спрашивают латиницей, а найтись она обязана та же."""
    assert [p.title for p in pick_franchise("Brother", POOL)] == ["Брат", "Брат 2"]


def test_a_third_name_of_the_picture_leads_to_it_too() -> None:
    """Третьим именем картину зовут раздачи, и это тот же вход в неё."""
    pool = [_picture("Брат", 1997, aliases=("bratan",))]

    assert [p.title for p in pick_franchise("Bratan", pool)] == ["Брат"]


def test_a_query_the_catalogue_does_not_answer_gets_nothing() -> None:
    """Пустой ответ честнее подставленного соседа: включать не то нельзя."""
    assert pick_franchise("Матрица", POOL) == []
