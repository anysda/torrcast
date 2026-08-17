"""Проверяет перебор имён, под которыми статья может лежать в Википедии."""

from torrcast.domain.facts.titles_for import titles_for


def test_article_names_walk_from_the_plain_title_to_the_qualified_one() -> None:
    """«Тачки 2» лежат под своим именем, «Моана» — под уточнением в скобках."""
    assert titles_for("Тачки 2", 2011)[0] == "Тачки 2"
    assert "Моана (мультфильм)" in titles_for("Моана", 2016)
    assert "Моана (фильм, 2026)" in titles_for("Моана", 2026)
    # Раздачи подписывают старое кино развёрнуто - короткое имя тоже надо попробовать.
    assert "Моана" in titles_for("Моана: романтика золотого века", 1926)


def test_case_variants_of_the_plain_name_are_tried_too() -> None:
    """Регистр внутри слова Википедия не чинит - пробуем заглавные слова и нижний регистр.

    «breaking bad» уходит в «Breaking bad» и мимо статьи, а редирект есть с «Breaking Bad»:
    без этого варианта прямая выборка промахивалась и справка уходила в медленный поиск.
    """
    names = titles_for("breaking bad", None)
    assert names[0] == "breaking bad", "само имя по-прежнему первое и в исходном виде"
    assert "Breaking Bad" in names, "заглавные слова - под ними и лежит редирект"
    assert "Twin Peaks" in titles_for("twin peaks", None)
    # Русскому имени регистровый вариант ничего не добавляет - лишних кандидатов не плодим.
    assert titles_for("Тачки 2", 2011).count("Тачки 2") == 1
