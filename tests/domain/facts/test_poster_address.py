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


def test_a_file_that_is_not_there_answers_with_nothing() -> None:
    """Имени из инфобокса на складе может не быть - тогда очередь запасного пути."""
    missing: dict[str, Any] = {"query": {"pages": [{"title": "File:Нет.jpg", "missing": True}]}}
    assert poster_address(missing) == ""
    assert poster_address({"query": {"pages": []}}) == ""
    assert poster_address({}) == ""
