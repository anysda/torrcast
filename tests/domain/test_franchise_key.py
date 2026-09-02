"""Зеркало :mod:`torrcast.domain.franchise_key`: ключ, общий у всех частей франшизы."""

from torrcast.domain.franchise_key import franchise_key


def test_every_part_of_a_franchise_answers_with_one_key() -> None:
    """Ключ на то и ключ: по нему части сходятся в одну картину, а не рассыпаются."""
    assert franchise_key("Матрица: Перезагрузка") == franchise_key("Матрица: Революция")


def test_a_title_that_is_a_franchise_by_itself_keeps_its_own_name() -> None:
    assert franchise_key("Брат") == "брат"


def test_two_different_franchises_do_not_share_a_key() -> None:
    assert franchise_key("Матрица") != franchise_key("Брат")


def test_the_adaptation_mark_does_not_start_a_second_franchise() -> None:
    """🔴 TC-969. Склейка сводила картины, а франшизы оставались две, и запрос по голому
    имени попадал по точному ключу в соседку без сидов - живой рой оставался вне меню."""
    assert franchise_key("Sakusei Byoutou The Animation") == franchise_key("Sakusei Byoutou")


def test_the_form_word_still_tells_a_film_from_a_series() -> None:
    """Слово ФОРМЫ тут не снимается: им и отличается «Naruto Shippuuden Movie» от сериала."""
    assert franchise_key("Naruto Shippuuden Movie") != franchise_key("Naruto Shippuuden")


def test_the_mark_standing_at_the_head_of_a_name_is_not_eaten() -> None:
    """🔴 Примета снимается только ХВОСТОМ: иначе у «The Animation Runner Kuromi» от имени
    остался бы огрызок «runner-kuromi», и починка развела бы одну картину надвое ровно тем
    способом, который лечит."""
    assert franchise_key("The Animation Runner Kuromi") == "the-animation-runner-kuromi"
