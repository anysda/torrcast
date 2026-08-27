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


def test_the_asked_type_leads_the_queue_of_qualifiers() -> None:
    """Уточнение своего типа идёт впереди чужого - до Википедии доезжают первые имена."""
    film = titles_for("Робокоп", 1987, "movie")
    series = titles_for("Робокоп", 1987, "tv")
    assert film.index("Робокоп (фильм, 1987)") < film.index("Робокоп (телесериал)")
    assert series.index("Робокоп (телесериал)") < series.index("Робокоп (фильм, 1987)")
    assert sorted(film) == sorted(series) == sorted(titles_for("Робокоп", 1987))
    assert film[0] == series[0] == "Робокоп", "голое имя первое при любом типе"


def test_an_unknown_type_leaves_the_queue_as_declared() -> None:
    """Тип не назван - подсказывать нечем, и порядок остаётся объявленным."""
    plain = titles_for("Робокоп", 1987)
    assert titles_for("Робокоп", 1987, "other") == plain
    assert titles_for("Робокоп", 1987, "") == plain
