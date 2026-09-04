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


def test_a_cartoon_series_is_asked_by_its_own_qualifier_ahead_of_alien_types() -> None:
    """Мультсериал зовётся своим словом, и зовётся ДО чужетипных уточнений.

    «Звёздные войны: Войны клонов» лежат под «(мультсериал, 2008)». Мера тут - место в
    очереди, а не присутствие имени: на меню из четырнадцати картин потолок волны
    (:func:`~torrcast.adapters.wiki.wiki_extracts.wiki_extracts`) пускает к Википедии
    четыре имени на картину, и уехавшее пятым зрителю не даёт ничего.
    """
    names = titles_for("Звёздные войны: Войны клонов", 2008, "tv")
    at = names.index("Звёздные войны: Войны клонов (мультсериал, 2008)")
    assert at < names.index("Звёздные войны: Войны клонов (мультфильм)")
    assert at < names.index("Звёздные войны: Войны клонов (мультфильм, 2008)")
    assert at < names.index("Звёздные войны: Войны клонов (фильм, 2008)")
    assert at <= 3, "имя, уехавшее за потолок волны, описания зрителю не приносит"


def test_an_unknown_type_leaves_the_queue_as_declared() -> None:
    """Тип не назван - подсказывать нечем, и порядок остаётся объявленным."""
    plain = titles_for("Робокоп", 1987)
    assert titles_for("Робокоп", 1987, "other") == plain
    assert titles_for("Робокоп", 1987, "") == plain


def test_a_shortened_name_is_not_offered_when_a_neighbour_is_called_by_it() -> None:
    """Имя соседа по вопросу - чужой адрес, а не кандидат отрезанного подзаголовка.

    🔴 TC-957. «Титаник: анатомия катастрофы» 1997 года отрезается до «Титаника», и
    кандидат «Титаник (фильм, 1997)» - это статья соседа по меню. Год у соседа ТОТ ЖЕ, и
    сверка года такую подмену пропускала: документальная лента печаталась с описанием и
    хронометражем кэмероновского «Титаника».
    """
    names = titles_for("Титаник: анатомия катастрофы", 1997, "movie", ["Титаник"])

    assert names[0] == "Титаник: анатомия катастрофы", "своё полное имя остаётся первым"
    assert "Титаник" not in names
    assert "Титаник (фильм, 1997)" not in names


def test_a_shortened_name_still_leads_to_the_article_when_nobody_claims_it() -> None:
    """Спроса на короткое имя нет - оно по-прежнему кандидат: статья названа короче.

    «Моана: романтика золотого века» лежит под «Моаной», и отказ от отрезанного имени
    ради одного соседа отнял бы справку у всех остальных.
    """
    alone = titles_for("Моана: романтика золотого века", 1926)

    assert "Моана" in alone
    assert "Моана" in titles_for("Моана: романтика золотого века", 1926, "", ["Тачки"])
    assert alone == titles_for(
        "Моана: романтика золотого века", 1926, "", ["Моана: романтика золотого века"]
    ), "своё же имя в списке спрошенных себя не отменяет"


def test_the_name_is_asked_in_the_typography_of_the_section() -> None:
    """Прямые кавычки раздачи заменяются ёлочками раздела прямо в голом имени."""
    names = titles_for('Читаем "Блокадную книгу"', 2009, "movie")
    assert names[0] == "Читаем «Блокадную книгу»"


def test_the_period_form_stands_right_behind_the_bare_name() -> None:
    """Место в очереди тут и есть смысл: за уточнениями форма до постера не доедет."""
    names = titles_for('Рерберг и Тарковский: Обратная сторона "Сталкера"', 2009, "movie")
    assert names[1] == "Рерберг и Тарковский. Обратная сторона «Сталкера»"


def test_a_name_without_a_subtitle_keeps_its_queue_untouched() -> None:
    """Двоеточия нет - и лишнего имени нет: очередь та же, что была."""
    assert "." not in " ".join(titles_for("Матрица", 1999, "movie"))
