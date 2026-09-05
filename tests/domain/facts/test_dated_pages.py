"""Зеркало :mod:`torrcast.domain.facts.dated_pages`: статьи вместе со сверкой их года."""

from torrcast.domain.facts.dated_pages import dated_pages
from torrcast.domain.json_value import JsonValue

REPLY: JsonValue = {
    "query": {
        "redirects": [{"from": "Паразиты (фильм, 2019)", "to": "Паразиты (фильм)"}],
        "pages": [
            {
                "title": "Паразиты (фильм)",
                "langlinks": [{"lang": "en", "title": "Parasite (2019 film)"}],
                "pageprops": {"wikibase_item": "Q61448040"},
                "categories": [{"title": "Категория:Фильмы Республики Корея"}],
            },
            {
                "title": "Матрица (фильм)",
                "langlinks": [{"lang": "en", "title": "The Matrix"}],
                "pageprops": {"wikibase_item": "Q83495"},
                "categories": [{"title": "Категория:Фильмы 1999 года"}],
            },
            {"title": "Паразит", "missing": True},
        ],
    }
}


def test_the_asked_name_is_read_along_with_the_page_it_led_to() -> None:
    """🔴 Само перенаправление «Паразиты (фильм, 2019)» и есть подтверждение года.

    Статья, в которую оно ведёт, называется без года, и читай мы только её, год этой
    находки пришлось бы спрашивать у Wikidata отдельным походом.
    """
    rows = dated_pages(REPLY, ["Паразиты (фильм, 2019)"])
    assert [row.page for row in rows] == ["Parasite (2019 film)"]
    assert rows[0].years == frozenset({2019})
    assert rows[0].entity == "Q61448040"


def test_the_year_of_the_categories_is_taken_when_the_name_keeps_quiet() -> None:
    """Категории приезжают тем же запросом и стоят поэтому ноль лишних походов."""
    rows = dated_pages(REPLY, ["Матрица (фильм)"])
    assert rows[0].years == frozenset({1999})
    assert rows[0].kinds == frozenset({"movie"})


def test_the_order_of_the_asked_names_is_the_order_of_trust() -> None:
    """Имена спрошены пачкой, а разбираются по одному: порядок задаём мы, а не ответ."""
    rows = dated_pages(REPLY, ["Матрица (фильм)", "Паразиты (фильм, 2019)"])
    assert [row.page for row in rows] == ["The Matrix", "Parasite (2019 film)"]


def test_a_page_that_is_not_there_gives_no_row_at_all() -> None:
    """Пустышка статьёй не считается, и повтор одной статьи в список не попадает дважды."""
    assert dated_pages(REPLY, ["Паразит"]) == []
    rows = dated_pages(REPLY, ["Паразиты (фильм, 2019)", "Паразиты (фильм)"])
    assert len(rows) == 1, f"одна статья приехала дважды: {rows}"


def test_the_english_reply_is_read_by_its_own_title_and_not_by_a_link() -> None:
    """У части находок русской статьи нет вовсе, и английская сама себе искомая."""
    reply: JsonValue = {
        "query": {
            "pages": [{"title": "Armitage: Dual Matrix", "pageprops": {"wikibase_item": "Q42"}}]
        }
    }
    rows = dated_pages(reply, ["Armitage: Dual Matrix"], linked=False)
    assert [row.page for row in rows] == ["Armitage: Dual Matrix"]
    assert [row.source for row in rows] == [""], "у английского ответа русской половины нет"


def test_a_russian_article_without_an_english_pair_is_kept_for_its_own_poster() -> None:
    """🔴 Ссылка на английскую статью - не пропуск: постер русская держит свой.

    Пока такая статья выбрасывалась целиком, картинки лишались ровно те картины, про
    которые английский раздел статьи не завёл.
    """
    reply: JsonValue = {
        "query": {
            "pages": [
                {
                    "title": "Чернобыль: Зона отчуждения. Финал",
                    "categories": [{"title": "Категория:Фильмы 2019 года"}],
                }
            ]
        }
    }
    rows = dated_pages(reply, ["Чернобыль: Зона отчуждения. Финал"])
    assert [row.page for row in rows] == [""], "английской пары у неё нет"
    assert [row.source for row in rows] == ["Чернобыль: Зона отчуждения. Финал"]
    assert [sorted(row.years) for row in rows] == [[2019]], "год сверяется как и прежде"


def test_the_kind_in_the_name_is_taken_from_the_heading_and_not_from_the_asked_name() -> None:
    """🔴 Спросить мы вправе что угодно, а разводит одноимённое сам раздел.

    «Паразиты (фильм, 2019)» - имя из нашей же очереди кандидатов, и Википедия ведёт им
    на «Паразиты (фильм)». Читай мы спрошенное имя, разведённой оказалась бы всякая
    картина, которую очередь спросила с уточнением, - в том числе стоящая под голым
    именем антология, и постера ей опять не досталось бы.
    """
    rows = dated_pages(REPLY, ["Паразиты (фильм, 2019)"])
    assert [row.named for row in rows] == ["movie"], "тёзка другого рода не названа"


def test_an_article_under_a_bare_name_says_so_with_an_empty_word() -> None:
    """Голое имя означает, что тёзки другого рода у картины нет: делить его не с кем."""
    reply: JsonValue = {
        "query": {
            "pages": [
                {
                    "title": "Аниматрица",
                    "langlinks": [{"lang": "en", "title": "The Animatrix"}],
                    "categories": [{"title": "Категория:Мультфильмы 2003 года"}],
                }
            ]
        }
    }
    rows = dated_pages(reply, ["Аниматрица"])
    assert [row.named for row in rows] == [""]
    assert [row.kinds for row in rows] == [frozenset({"movie"})], "род статьи прежний"
