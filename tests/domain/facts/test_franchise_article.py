"""Проверяет опознание статьи о франшизе там, где спрошена её картина с подзаголовком."""

from torrcast.domain.facts.franchise_article import franchise_article


def test_a_franchise_article_does_not_answer_for_a_subtitled_picture() -> None:
    """🔴 TC-779. «Тачки: Байки Мэтра» - это не «Тачки», как бы ни совпадало начало имени."""
    assert franchise_article("Тачки: Байки Мэтра", "Тачки")
    assert franchise_article("Тачки: Байки Мэтра", "Тачки (мультфильм)")
    assert franchise_article("Звёздный путь: Следующее поколение", "Звёздный путь")


def test_the_same_name_is_the_asked_picture() -> None:
    """Заголовок и запрос совпали - статья названа ровно тем, что спросили."""
    assert not franchise_article("Тачки", "Тачки")
    assert not franchise_article("Мультачки: Байки Мэтра", "Мультачки: Байки Мэтра")


def test_a_numbered_heading_is_a_picture_and_not_a_franchise() -> None:
    """«Один дома 2» - уже картина, и подзаголовок называет её же, а не соседнюю."""
    assert not franchise_article("Один дома 2: Затерянный в Нью-Йорке", "Один дома 2")


def test_a_numbered_query_is_left_to_the_older_rule() -> None:
    """Номер части приставляется к имени обратно - там паспорт годится (TC-480)."""
    assert not franchise_article("тачки 2", "Тачки")


def test_an_unrelated_heading_is_not_a_franchise_of_the_query() -> None:
    """Начало имени не совпало - о франшизе речи нет вовсе."""
    assert not franchise_article("Тачки: Байки Мэтра", "Мультачки")
    assert not franchise_article("Психо", "Психоз")
