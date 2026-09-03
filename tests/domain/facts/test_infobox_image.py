"""Зеркало разбора инфобокса: имя постера из вики-текста и отказ на всём остальном."""

from __future__ import annotations

from torrcast.domain.facts.infobox_image import infobox_image

#: Снятая с en.wikipedia первая секция «Interstellar (film)», урезанная до нужного.
#: Записана, а не собрана из вопроса: подделка обязана быть второй стороной.
INTERSTELLAR = """{{Infobox film
| name = Interstellar
| image = Interstellar film poster.jpg
| image_size = 250px
| alt = Spacecraft in the shadow of a planet
| caption = Theatrical release poster
| director = [[Christopher Nolan]]
}}
'''Interstellar''' is a 2014 epic science fiction film."""


def test_the_infobox_line_names_the_poster_file() -> None:
    assert infobox_image(INTERSTELLAR) == "Interstellar film poster.jpg"


def test_the_layout_lines_are_not_the_picture() -> None:
    """`image_size` стоит следом за `image` и описывает вёрстку, а не файл.

    Возьмись правило за всё, что начинается с `image`, за адресом уехало бы «250px», а
    `imageinfo` ответил бы на него пустотой - молча, на каждой картине сразу.

    Порядок параметров в разметке ничей не держит: у «Чернобыля» и «Уэнздей» строки
    вёрстки стоят вплотную к `image`, и переставить их местами волен любой правщик.
    Поэтому проверяется не только отказ на одной вёрстке, но и то, что строка вёрстки
    ВЫШЕ настоящей не перехватывает ответ.
    """
    assert infobox_image("| image_size = 250px\n| image_alt = poster\n") == ""
    assert infobox_image("| image_size = 250px\n| image = Solaris poster.jpg\n") == (
        "Solaris poster.jpg"
    )


def test_the_wrappers_around_the_name_are_stripped() -> None:
    """Вставку пишут и разметкой; тогда имя стоит внутри неё, а следом идут подписи."""
    assert infobox_image("| image = [[File:Stalker poster.jpg|250px|alt=Poster]]\n") == (
        "Stalker poster.jpg"
    )
    assert infobox_image("| image = Image:Solaris poster.jpg\n") == "Solaris poster.jpg"


def test_what_is_not_a_file_name_is_not_taken_for_one() -> None:
    """Шаблон и комментарий редактора стоят на том же месте, но файлом не являются.

    Без этого гейта за адресом уезжало бы слово «multiple image», а `imageinfo` на него
    отвечал бы пустотой - то есть картина оставалась бы без картинки МОЛЧА, вместо того
    чтобы честно уйти на запасной путь.
    """
    assert infobox_image("| image = {{multiple image\n | image1 = a.jpg\n}}\n") == ""
    assert infobox_image("| image = <!-- see talk page -->\n") == ""
    assert infobox_image("| image =\n") == ""
    assert infobox_image("") == ""


def test_a_series_titlecard_counts_and_a_vector_one_too() -> None:
    """У сериалов в `image` лежит заставка или логотип, и это тоже ответ статьи."""
    assert infobox_image("| image = Sherlock titlecard.jpg\n") == "Sherlock titlecard.jpg"
    assert infobox_image("| image = Wednesday (Netflix TV series) logo.svg\n") == (
        "Wednesday (Netflix TV series) logo.svg"
    )
