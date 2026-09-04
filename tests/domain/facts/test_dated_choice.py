"""Зеркало :mod:`torrcast.domain.facts.dated_choice`: два захода сверки года и их порядок."""

from torrcast.domain.facts.ask import Ask
from torrcast.domain.facts.dated import Dated
from torrcast.domain.facts.dated_choice import dated_choice

#: Мультфильм 1994 года: его статья лежит ровно под оригинальным именем римейка.
LION_1994 = Dated("The Lion King", "Q36479", frozenset({1994}), frozenset({"movie"}))
#: Своя статья римейка: имя у неё с уточнением года, а не голое.
LION_2019 = Dated("The Lion King (2019 film)", "Q29579", frozenset({2019}), frozenset({"movie"}))
FELLOWSHIP = Dated(
    "The Lord of the Rings: The Fellowship of the Ring",
    "Q127367",
    frozenset({2001}),
    frozenset({"movie"}),
)


def test_the_reissue_pass_never_runs_while_the_picture_has_an_article_of_its_own() -> None:
    """🔴 ОТРИЦАТЕЛЬНАЯ ПРОБА на порядок заходов: поставь их рядом - и «Король Лев» 2019
    года получит картинку мультфильма 1994-го.

    Оригинальное имя у них одно и то же, «The Lion King», и точное совпадение имени
    сработало бы на старой статье. Держит римейк не признак строки, а пустота первого
    захода: своя статья у него есть, значит перевыпуском он не был.
    """
    ask = Ask("Король Лев", 2019, "movie", "The Lion King")
    chosen = dated_choice(ask, [LION_1994, LION_2019], {})
    assert chosen == [LION_2019], "римейку досталась картинка старого мультфильма"


def test_the_reissue_pass_answers_where_the_plain_one_left_an_empty_place() -> None:
    """Своей статьи под 2011 год нет ни одной, и год раздачи оказывается годом издания."""
    ask = Ask(
        "Властелин колец: Братство кольца",
        2011,
        "movie",
        "The Lord of the Rings: The Fellowship of the Ring",
    )
    assert dated_choice(ask, [FELLOWSHIP], {}) == [FELLOWSHIP]


def test_a_picture_with_neither_pass_answering_keeps_its_empty_place() -> None:
    """Пустая строка честна: чужой картинки тут не появляется ни на одном заходе."""
    ask = Ask("Король Лев", 2019, "movie", "")
    assert dated_choice(ask, [LION_1994], {}) == []
