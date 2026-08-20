"""Проверяет главный разбор справки: статьи-кандидаты в паспорт картины."""

from typing import Any

from tests.articles import (
    ATTACK_FILM,
    BICYCLE_THIEVES,
    BREAKING_BAD,
    CARS,
    CLIMBERS,
    FARGO_SERIES,
    FELLOWSHIP,
    HP_AZKABAN,
    HP_FRANCHISE,
    HP_PHOENIX,
    HP_PRINCE,
    JUDGMENT,
    MOANA,
    MOANA_2026,
    NATIVE_SERIES,
    NINE_CARTOON,
    NINE_MUSICAL,
    NOT_CINEMA,
    SALTBURN,
    SAMURAI_7,
    SEVEN_SAMURAI,
    SURPRISED,
    TERMINATOR,
    UTENA,
    WEDNESDAY,
    WHISPERS,
    page,
)
from torrcast.domain.facts.read_origin import read_origin


def test_wikipedia_knows_better_than_us_how_the_asked_name_is_spelled() -> None:
    """Имя назвали мы сами, до статьи довело перенаправление - спорить с ним нечем.

    «Уэнсдей» в русской Википедии пишется «Уэнздей», и прежняя сверка заголовка
    (:func:`akin`) отвергала статью, которую сама же Википедия и выдала: справка молчала
    ровно там, где знала ответ, и поиску нечем было добирать.
    """
    assert read_origin([page("Уэнздей", WEDNESDAY)], "Уэнсдей", trusted=True).title == "Wednesday"


def test_a_namesake_from_the_search_is_still_checked_by_its_heading() -> None:
    """Послабление касается только имён, которые мы назвали сами."""
    hannibal = page("Ганнибал: Восхождение", CLIMBERS)
    assert not read_origin([hannibal], "Восхождение")
    assert read_origin([hannibal], "Ганнибал: Восхождение").year == 2019


def test_a_picture_whose_type_is_spelled_out_still_gives_up_its_original_name() -> None:
    """Тип картины бывает описательным - оригинал от этого никуда не девается."""
    breaking = page("Во все тяжкие", BREAKING_BAD)
    found = read_origin([breaking], "Во все тяжкие", trusted=True)
    assert found.title == "Breaking Bad"
    assert found.year == 2008
    assert found.name == "Во все тяжкие"
    # Поиском Википедии - тот же ответ: заголовок статьи под запрос подходит.
    assert read_origin([breaking], "Во все тяжкие").title == "Breaking Bad"


def test_an_article_that_is_not_about_cinema_gives_nothing_at_all() -> None:
    """Главное ограждение: человек, город, компания и книга паспорта не получают.

    Скобка с латиницей есть у кого угодно - «(англ. William Bradley Pitt)», «(англ. Dune)»
    у романа Герберта, - и стоит пустить такую статью дальше гейта, как справка молча
    выдаст чужую строку за оригинальное название картины.
    """
    for heading, extract in NOT_CINEMA.items():
        found = page(heading, extract, english=heading)
        asked = heading.split(" (")[0]
        assert not read_origin([found], asked, trusted=True), heading
        assert not read_origin([found], asked), heading


def test_the_original_name_comes_from_the_english_article_when_the_text_has_none() -> None:
    """У аниме в скобке иероглифы, а не латиница - имя берётся из английской статьи."""
    utena = page("Юная революционерка Утэна", UTENA, english="Revolutionary Girl Utena")
    assert read_origin([utena], "Утэна", trusted=True).title == "Revolutionary Girl Utena"
    attack = page("Атака титанов (фильм)", ATTACK_FILM, english="Attack on Titan")
    assert read_origin([attack], "атака титанов", trusted=True).title == "Attack on Titan"


def test_the_english_article_does_not_outrank_the_original_in_the_text() -> None:
    """Скобка первой фразы точнее: там оригинал, а не английское прокатное имя."""
    both = page("Уэнздей", WEDNESDAY, english="Wednesday (TV series)")
    assert read_origin([both], "Уэнсдей", trusted=True).title == "Wednesday"


def test_a_film_does_not_answer_for_the_series_it_was_made_from() -> None:
    """Худший брак справки: спросили сериал, а она уверенно назвала его экранизацию."""
    film = page("Атака титанов (фильм)", ATTACK_FILM, english="Attack on Titan")
    assert not read_origin([film], "атака титанов", trusted=True, series=True)
    assert not read_origin([film], "атака титанов", series=True)
    # Спросили фильм - фильм и получите: гейт разводит типы, а не запрещает картину.
    found = read_origin([film], "атака титанов", trusted=True, series=False)
    assert found.title == "Attack on Titan"
    assert found.year == 2015


def test_a_type_the_article_never_names_does_not_silence_it() -> None:
    """Гейт типа отказывает на противоречии, а не на молчании."""
    breaking = page("Во все тяжкие", BREAKING_BAD)
    assert read_origin([breaking], "Во все тяжкие", trusted=True, series=True).year == 2008
    assert not read_origin([breaking], "Во все тяжкие", trusted=True, series=False)
    # Тип неизвестен - сверять нечем, и гейт молчит: так ходит режим «оба типа».
    assert read_origin([breaking], "Во все тяжкие", trusted=True, series=None).year == 2008


def test_the_year_of_a_neighbour_in_the_franchise_is_not_this_pictures_year() -> None:
    """Год паспорта сильнее выдачи, поэтому чужой год - это та же подмена картины."""
    fargo = page("Фарго (телесериал)", FARGO_SERIES, english="Fargo")
    found = read_origin([fargo], "фарго", trusted=True, series=True)
    assert found.title == "Fargo", "саму картину справка по-прежнему знает"
    assert found.year is None, "1996 - год фильма, а не этого сериала"


def test_the_same_words_in_another_order_still_give_up_the_picture() -> None:
    """«Крики и шёпот» - это статья «Шёпоты и крики», и оригинал у неё есть."""
    whispers = page("Шёпоты и крики", WHISPERS, english="Cries and Whispers")
    assert read_origin([whispers], "Крики и шёпот").title == "Viskningar och rop"


def test_the_pointer_line_does_not_hand_the_classic_to_its_remake() -> None:
    """Указатель отрезан - и фильм Куросавы больше не читается как сериал."""
    pages = [page("Семь самураев", SEVEN_SAMURAI, english="Seven Samurai")]
    assert read_origin(pages, "Семь самураев", trusted=True, series=False).title == "Seven Samurai"
    # А сам ремейк остаётся собой: указатель отрезан только там, где он есть.
    remake = page("7 самураев", SAMURAI_7, english="Samurai 7")
    assert read_origin([remake], "7 самураев", trusted=True).title == "Samurai 7"


def test_a_classic_that_never_says_the_word_film_still_gives_its_original() -> None:
    """Паспортная формула произведения: название в кавычках, жанр и год выхода."""
    thieves = page("Похитители велосипедов", BICYCLE_THIEVES, english="Bicycle Thieves")
    found = read_origin([thieves], "Похитители велосипедов", trusted=True, series=False)
    assert found.title == "Ladri di biciclette"
    assert found.year == 1948


def test_a_bare_franchise_name_is_answered_by_the_franchise_or_by_nothing() -> None:
    """Голое имя франшизы частью франшизы не отвечается.

    На «гарри поттер» справка приносила паспорт ПЯТОГО фильма: статья о самой серии не
    проходила киношный гейт («серия фильмов» - косвенный падеж), а сверка заголовка
    принимала любое продолжение имени, и побеждал тот, кого выше поставил поиск.
    """
    parts = [
        page("Гарри Поттер и Орден Феникса (фильм)", HP_PHOENIX),
        page("Гарри Поттер и Принц-полукровка (фильм)", HP_PRINCE),
        page("Гарри Поттер и узник Азкабана (фильм)", HP_AZKABAN),
    ]
    whole = page("Гарри Поттер (серия фильмов)", HP_FRANCHISE, english="Harry Potter (film series)")
    found = read_origin([whole, *parts], "гарри поттер")
    assert found.title == "Harry Potter", "имя франшизы - ровно то, которым её подписывают"
    assert found.name == "Гарри Поттер"
    assert found.year is None, "у серии фильмов года нет, и выдумывать его нечем"
    # Статьи о серии нет - молчание: выбрать часть за человека справка не вправе.
    assert not read_origin(parts, "гарри поттер")
    # Продолжение одно - это уточнение имени, а не выбор части: так находится «Кингсман».
    assert read_origin(list(parts[:1]), "гарри поттер").title.startswith("Harry Potter and")


def test_a_numbered_part_is_never_answered_by_the_whole_franchise() -> None:
    """🔴 TC-480. Спросили часть N, отвечает имя франшизы - это догадка, и года у неё нет."""
    whole = page("Терминатор (фильм)", TERMINATOR, english="The Terminator")
    found = read_origin([whole], "терминатор 2", series=False)
    assert found.title == "The Terminator", "имя латиницей годится: номер части у него отрезан"
    assert found.year is None, "год ПЕРВОЙ картины спрошенной части не паспорт"
    assert found.guessed, "статья названа не тем, что спросили - так и говорим вслух"

    # Спрошенная часть в той же выдаче побеждает франшизу целиком, и она уже не догадка.
    part = page("Терминатор 2: Судный день", JUDGMENT, english="Terminator 2: Judgment Day")
    exact = read_origin([whole, part], "терминатор 2", series=False)
    assert (exact.title, exact.year, exact.guessed) == ("Terminator 2: Judgment Day", 1991, False)

    # Подзаголовок номером части не является: «Властелин колец» за «Братство кольца» отвечает.
    rings = page("Властелин колец (фильм)", FELLOWSHIP, english="The Lord of the Rings")
    named = read_origin([rings], "Властелин колец: Братство кольца", series=False)
    assert named.title == "The Lord of the Rings"
    assert not named.guessed, "имя без номера части статья носит целиком"


def test_a_localized_name_finds_the_shorter_article_without_taking_its_namesake() -> None:
    """🔴 TC-283. Два слова прокатного имени не должны заслонять нужную статью."""
    older = page(
        "Незнакомцы (фильм, 2008)",
        "«Незнакомцы» - американский фильм ужасов.",
        english="The Strangers",
    )
    wanted = page(
        "Незнакомцы (фильм, 2023)",
        "«Незнакомцы» - художественный фильм режиссёра Эндрю Хэйга.",
        english="All of Us Strangers",
    )
    found = read_origin([older, wanted], "Все мы незнакомцы", series=False)
    assert found.title == "All of Us Strangers"
    assert found.name == "Незнакомцы"
    assert found.guessed, "сокращённый заголовок остаётся догадкой, а не точным именем"


def test_an_almost_the_same_name_still_gives_up_its_picture() -> None:
    """Прошедшая сверку статья читается как выборка по имени - но всегда без года."""
    saltburn = page("Солтберн", SALTBURN, english="Saltburn (film)")
    surprised = page(
        "Человек, который удивил всех", SURPRISED, english="The Man Who Surprised Everyone"
    )
    assert read_origin([saltburn], "сальтберн", trusted=True).title == "Saltburn"
    found = read_origin([surprised], "мужчина который удивил всех", trusted=True)
    assert found.title == "The Man Who Surprised Everyone"
    assert found.name == "Человек, который удивил всех"


def test_the_reference_names_the_second_picture_of_the_same_year() -> None:
    """🔴 TC-371. Под одним именем и годом картин две - справка называет вторую."""
    pages: list[Any] = [
        {"title": "Девять (фильм)", "extract": NINE_MUSICAL},
        {"title": "9 (мультфильм, 2009)", "extract": NINE_CARTOON},
    ]
    found = read_origin(pages, "Девять", trusted=True, series=False)
    assert (found.title, found.year) == ("Nine", 2009)
    assert found.namesake == "9 (мультфильм, 2009)"


def test_a_namesake_of_another_year_is_not_an_ambiguity() -> None:
    """Одноимённые картины разных лет разводит год - и разводит его сам отбор."""
    pages: list[Any] = [
        {"title": "Моана (мультфильм)", "extract": MOANA},
        {"title": "Моана (фильм, 2026)", "extract": MOANA_2026.replace("режиссёра", "2026 года")},
    ]
    found = read_origin(pages, "Моана", trusted=True, series=False)
    assert (found.title, found.year) == ("Moana", 2016)
    assert not found.namesake, "год развёл картины - говорить не о чем"


def test_an_article_that_names_no_foreign_name_proves_the_picture_is_ours() -> None:
    """Первая фраза чужого имени не называет - паспорт несёт доказательство происхождения.

    Им и только им безымянная дорожка засчитывается за русскую
    (:func:`~torrcast.domain.facts.proven_native.proven_native`).
    """
    about = read_origin(
        [page("Тени исчезают в полдень", NATIVE_SERIES)], "Тени исчезают в полдень", trusted=True
    )

    assert about.native and about.title == ""


def test_a_hieroglyphic_original_is_a_named_one_and_proves_nothing() -> None:
    """🔴 TC-567. У аниме имя записано иероглифами: искать по нему нечего, но оно ЕСТЬ.

    Английской статьи у такой картины может не быть вовсе, и тогда паспорт уезжает с
    пустым оригиналом - ровно с таким же, какой бывает у отечественного кино. Прежде
    отбор звука читал эту пустоту как «картина наша» и отдавал зрителю японскую дорожку.
    """
    about = read_origin(
        [page("Юная революционерка Утэна", UTENA)], "Юная революционерка Утэна", trusted=True
    )

    assert about.title == "" and not about.native


def test_a_named_latin_original_leaves_no_room_for_the_proof() -> None:
    """Имя латиницей названо - доказывать нечего, признак молчит."""
    assert not read_origin([page("Тачки", CARS)], "Тачки", trusted=True).native
