"""Проверяет границу первой фразы статьи: скобки, кавычки, сокращения, указатель."""

from tests.articles import CARS, CLONE_WARS, SEVEN_SAMURAI
from torrcast.domain.facts.sentence import sentence


def test_a_dot_inside_a_bracket_or_a_quote_is_not_the_end_of_the_phrase() -> None:
    """Скобка с языком оригинала и точка внутри «ёлочек» фразу не кончают.

    Обе строки — живые: «(англ. Cars)» стоит в каждой второй статье о зарубежном кино,
    а название книги с точкой посередине приехало из статьи об «Оппенгеймере».
    """
    assert sentence(CARS).startswith("«Та́чки» (англ. Cars) — американский")
    book = (
        "«О́ппенгеймер» (англ. Oppenheimer) — триллер 2023 года, основанный на книге "
        "«Оппенгеймер. Триумф и трагедия Американского Прометея» (2004). Снят Syncopy."
    )
    assert sentence(book).endswith("(2004).")
    dune = (
        "«Дю́на» (англ. Dune), в титрах «Дюна: Часть первая» (англ. Dune: Part One) — "
        "американский фильм 2021 года режиссёра Дени Вильнёва. Это первая лента серии."
    )
    assert sentence(dune).endswith("Дени Вильнёва.")


def test_abbreviations_and_initials_do_not_break_the_phrase() -> None:
    """«т. е.», «реж.» и инициалы — сокращения, а не конец фразы."""
    initials = "«Сталкер» — фильм реж. А. А. Тарковского по повести Стругацких. Снят в Эстонии."
    assert sentence(initials).endswith("Стругацких.")
    same = "«Психо» — фильм ужасов, т. е. хоррор, 1960 года. Снят Альфредом Хичкоком."
    assert sentence(same).endswith("1960 года.")
    assert sentence("«2001» (англ. 2001: A Space Odyssey) — фильм 1968 года.").endswith("года.")


def test_the_pointer_line_at_the_top_is_not_the_pictures_own_sentence() -> None:
    """«О сериале см. статью 7 самураев.» - это разводка одноимённого, а не фраза о картине.

    Читая её первой фразой, справка видела у фильма Куросавы слово «сериале», отвергала
    его статью как чужой тип и уходила в соседнюю - аниме-ремейк, - откуда приносила
    ``Samurai 7`` оригиналом классики 1954 года.
    """
    assert sentence(SEVEN_SAMURAI).startswith("«Семь самура́ев»")


def test_the_pointer_without_the_word_see_is_cut_by_its_line_break() -> None:
    """«Не путать с ...» слова «см.» не содержит и точкой не кончается - и всё же шляпка.

    Читая её первой фразой, меню отдавало половину отведённой длины служебному указателю,
    а фраза о картине обрывалась многоточием (TC-908).
    """
    first = sentence(CLONE_WARS)
    assert first.startswith("«Звёздные во́йны: Во́йны кло́нов» (англ. Star Wars: The Clone Wars)")
    assert "Не путать" not in first
    assert first.endswith("Lucasfilm Animation Singapore.")


def test_a_description_that_legitimately_opens_with_a_quote_is_not_touched() -> None:
    """Шляпка УЗНАЁТСЯ по формуле, а не угадывается по первой кавычке или первому абзацу.

    Правило «выкинуть всё до кавычки» съело бы описание у каждой второй картины: русская
    Википедия открывает статью о кино ровно кавычкой. Абзац без известной формулы остаётся
    текстом статьи, даже если за ним идут другие абзацы.
    """
    assert sentence(CARS).startswith("«Та́чки» (англ. Cars) — американский")
    own = "«О́ко» (англ. The Eye) — фильм ужасов 2008 года.\n\nСнят братьями Пан."
    assert sentence(own).endswith("2008 года.")
