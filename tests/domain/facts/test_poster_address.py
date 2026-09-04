"""Зеркало :mod:`torrcast.domain.facts.poster_address`: адрес файла из ``imageinfo``."""

from __future__ import annotations

from typing import Any

from torrcast.domain.facts.poster_address import poster_address

#: Живой ответ ``imageinfo`` с ``iiurlwidth=500`` на логотип «Уэнздей»: сам файл -
#: вектор, а уменьшенная копия приезжает растром. Карточка плеера вектор не рисует.
WEDNESDAY: dict[str, Any] = {
    "query": {
        "pages": [
            {
                "title": "File:Wednesday (Netflix TV series) logo.svg",
                "imageinfo": [
                    {
                        "url": "https://upload.wikimedia.org/wikipedia/commons/1/1c/Wednesday.svg",
                        "thumburl": (
                            "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1c/"
                            "Wednesday.svg/500px-Wednesday.svg.png"
                        ),
                    }
                ],
            }
        ]
    }
}


def test_the_shrunk_copy_is_taken_first() -> None:
    """Она же и растр: вектору в карточке плеера не нарисоваться."""
    assert poster_address(WEDNESDAY).endswith("500px-Wednesday.svg.png")


def test_without_a_shrunk_copy_the_original_answers() -> None:
    """Ужимать нечего - файл уже мал; тогда идёт тот же файл, что лежит на складе."""
    payload: dict[str, Any] = {
        "query": {
            "pages": [
                {
                    "title": "File:Interstellar film poster.jpg",
                    "imageinfo": [{"url": "https://upload.wikimedia.org/a/Interstellar.jpg"}],
                }
            ]
        }
    }
    assert poster_address(payload) == "https://upload.wikimedia.org/a/Interstellar.jpg"


def _file(**sides: int) -> dict[str, Any]:
    """Ответ ``imageinfo`` про один файл; стороны те, что назвала проба."""
    return {
        "query": {
            "pages": [
                {
                    "title": "File:Один.jpg",
                    "imageinfo": [{"thumburl": "https://upload.wikimedia.org/один.jpg", **sides}],
                }
            ]
        }
    }


def test_a_picture_wider_than_it_is_tall_never_becomes_an_address() -> None:
    """🔴 Живая «Аниматрица»: ``Theanimatrix-logo.svg`` приезжает копией 500x144.

    Это вордмарк - надпись с названием на тёмном фоне, - и карточка плеера рисует им
    широкую тёмную полосу, по которой картину не узнать. Отказ выносится ДО загрузки
    байтов, чтобы очередь кандидатов пошла дальше сама.
    """
    assert poster_address(_file(thumbwidth=500, thumbheight=144)) == ""
    assert poster_address(_file(width=512, height=147)) == ""


def test_an_upright_picture_and_a_square_one_pass() -> None:
    """Постер выше, чем шире («Интерстеллар» 220x326); квадрат тоже не вордмарк.

    Лежачесть - строгое превышение: откажи мы квадрату, отсев съел бы обложки сборников.
    """
    assert poster_address(_file(thumbwidth=500, thumbheight=741)).endswith("один.jpg")
    assert poster_address(_file(thumbwidth=500, thumbheight=500)).endswith("один.jpg")


def test_the_sides_of_the_shrunk_copy_outweigh_the_sides_of_the_original() -> None:
    """Уезжает в карточку копия, по ней и судим; пропорцию ``iiurlwidth`` не искажает."""
    assert poster_address(_file(thumbwidth=500, thumbheight=638, width=1995, height=2547))
    assert poster_address(_file(thumbwidth=500, thumbheight=144, width=512, height=147)) == ""


def test_a_picture_of_unknown_sides_is_let_through() -> None:
    """🔴 Молчание про стороны - «пропустить», а не «отказать».

    Стороны приезжают полями ответа. Откажи мы по их отсутствию - смена формата ответа
    Википедии оставила бы без постеров ВСЕ картины разом, а выглядело бы это как честное
    «постера не нашлось»: ни одна проба не покраснела бы, а карточка молча показывала бы
    кадр до конца жизни склада.
    """
    assert poster_address(_file()).endswith("один.jpg")
    assert poster_address(_file(thumbwidth=500)).endswith("один.jpg")
    assert poster_address(WEDNESDAY).endswith("500px-Wednesday.svg.png")


def test_a_file_that_is_not_there_answers_with_nothing() -> None:
    """Имени из инфобокса на складе может не быть - тогда очередь запасного пути."""
    missing: dict[str, Any] = {"query": {"pages": [{"title": "File:Нет.jpg", "missing": True}]}}
    assert poster_address(missing) == ""
    assert poster_address({"query": {"pages": []}}) == ""
    assert poster_address({}) == ""
