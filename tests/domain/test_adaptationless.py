"""Зеркало :mod:`torrcast.domain.adaptationless`: примета экранизации против вида."""

from torrcast.domain.adaptationless import _adaptationless


def test_the_adaptation_mark_is_dropped_from_the_tail() -> None:
    """«X The Animation» и «X» - одна работа, а выдача звала её то так, то этак."""
    assert _adaptationless("sakusei-byoutou-the-animation") == "sakusei-byoutou"
    assert _adaptationless("love-me-kaede-to-suzu-the-anime") == "love-me-kaede-to-suzu"


def test_the_mark_at_the_head_is_the_name_itself_and_is_not_dropped() -> None:
    """🔴 Примета - ПРИПИСКА к готовому имени, и снятие её не с хвоста съедает имя: у «The
    Animation Runner Kuromi» осталось бы «runner-kuromi», то есть починка развела бы одну
    картину надвое ровно тем способом, который лечит. Закрытый список от этого не спасает -
    ведущее «The» самого имени даёт полное совпадение, - спасает только позиция."""
    assert _adaptationless("the-animation-runner-kuromi") == "the-animation-runner-kuromi"


def test_the_mark_in_the_middle_is_not_a_tail_and_the_key_stays_whole() -> None:
    """Замерено: в середине примета стоит у 8 строк выдачи, и все 8 остаются отдельными
    картинами по мусорному хвосту ЗА приметой, - снятие там не меняет ни пункта меню.
    Номер после приметы означает ровно то же: примета тут не хвост."""
    assert _adaptationless("sakusei-byoutou-the-animation-10") == "sakusei-byoutou-the-animation-10"
    tachibana = "sakusei-byoutou-the-animation-tachibana-hen"
    assert _adaptationless(tachibana) == tachibana


def test_a_word_outside_the_closed_list_is_not_the_mark() -> None:
    """Голое «animation» стоит в живых именах само по себе, и списком бережётся примета."""
    assert _adaptationless("animation-runner-kuromi") == "animation-runner-kuromi"
    assert _adaptationless("the-animatrix") == "the-animatrix"


def test_a_key_made_of_the_mark_alone_is_kept_whole() -> None:
    """Пустого ключа не отдаём: снимать больше нечего, а ключ нужен."""
    assert _adaptationless("the-animation") == "the-animation"
