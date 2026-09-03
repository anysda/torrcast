"""Зеркало :mod:`torrcast.domain.facts.english_pages`: очередь английских адресов."""

from __future__ import annotations

from typing import Any

from torrcast.domain.facts.english_pages import english_pages

#: Живой ответ ru.wikipedia на очередь имён «Брата»: голое имя ведёт в статью про
#: РОДСТВО, и её межъязыковая ссылка честно указывает на английское ``Brother``, где
#: инфобокса с постером нет и быть не может. Фильм лежит следующим кандидатом.
BROTHER: dict[str, Any] = {
    "query": {
        "pages": [
            {"title": "Брат", "langlinks": [{"lang": "en", "title": "Brother"}]},
            {
                "title": "Брат (фильм, 1997)",
                "langlinks": [{"lang": "en", "title": "Brother (1997 film)"}],
            },
        ]
    }
}


def test_the_answers_keep_the_order_the_names_were_asked_in() -> None:
    """Порядок - это и есть доверие: первым идёт самое точное имя картины.

    Читателю инфобокса он нужен целиком: у «Брата» первый адрес отвечает статьёй про
    родство без постера, и правильный ответ лежит ВТОРЫМ.
    """
    assert english_pages(BROTHER, ["Брат", "Брат (фильм, 1997)"]) == [
        "Brother",
        "Brother (1997 film)",
    ]


def test_a_name_asked_later_does_not_jump_the_queue() -> None:
    """Спросили в другом порядке - и ответ идёт в том же другом порядке."""
    assert english_pages(BROTHER, ["Брат (фильм, 1997)", "Брат"]) == [
        "Brother (1997 film)",
        "Brother",
    ]


def test_a_disambiguation_page_never_becomes_an_address() -> None:
    """Страница значений отвечает ссылкой на такую же страницу значений чужого раздела.

    Уйди она в очередь - за постером поехал бы запрос к статье-перечню, а инфобокса там
    нет: ответом стала бы не ошибка, а МОЛЧАЛИВАЯ пустота.
    """
    payload: dict[str, Any] = {
        "query": {
            "pages": [
                {
                    "title": "Начало",
                    "pageprops": {"disambiguation": ""},
                    "langlinks": [{"lang": "en", "title": "Beginning"}],
                },
                {
                    "title": "Начало (фильм, 2010)",
                    "langlinks": [{"lang": "en", "title": "Inception"}],
                },
            ]
        }
    }
    assert english_pages(payload, ["Начало", "Начало (фильм, 2010)"]) == ["Inception"]


def test_a_page_that_is_not_there_and_a_page_without_a_link_answer_with_nothing() -> None:
    """Английской статьи может не быть вовсе - тогда постеру взяться неоткуда."""
    payload: dict[str, Any] = {
        "query": {
            "pages": [
                {"title": "Внутри Лапенко", "extract": ""},
                {"title": "Внутри Лапенко (сериал)", "missing": True},
            ]
        }
    }
    assert english_pages(payload, ["Внутри Лапенко", "Внутри Лапенко (сериал)"]) == []


def test_the_same_address_is_named_once() -> None:
    """Разные имена картины сходятся в одну статью - и адрес спрашивать дважды незачем."""
    payload: dict[str, Any] = {
        "query": {
            "redirects": [{"from": "Матрица", "to": "Матрица (фильм)"}],
            "pages": [
                {
                    "title": "Матрица (фильм)",
                    "langlinks": [{"lang": "en", "title": "The Matrix"}],
                }
            ],
        }
    }
    assert english_pages(payload, ["Матрица", "Матрица (фильм)"]) == ["The Matrix"]
