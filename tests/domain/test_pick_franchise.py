"""Зеркало :mod:`torrcast.domain.pick_franchise`: какие картины отвечают запросу."""

from dataclasses import replace

from torrcast.domain.cluster import cluster
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release

_NAMES = [
    "Тачки: Байки Мэтра / Cars Toon: Mater's Tall Tales (2008) BDRip 1080p",
    "Тачки: Байки Мэтра / Cars Toon: Mater's Tall Tales (2010) BDRip 1080p",
    "Тачки / Cars (2006) BDRip 1080p",
    "Тачки 2 / Cars 2 (2011) BDRip 1080p",
]


def _pictures() -> list[Picture]:
    return cluster([parse_release_name(name) for name in _NAMES])


def _picture(
    title: str,
    year: int,
    original: str | None = None,
    part: int | None = None,
    aliases: tuple[str, ...] = (),
) -> Picture:
    return Picture(
        title=title,
        year=year,
        original=original,
        part=part,
        aliases=aliases,
        releases=[Release(raw_name=title, title=title)],
    )


FIRST = _picture("Брат", 1997, "Brother")
SECOND = _picture("Брат 2", 2000, "Brother 2", part=2)
STRANGER = _picture("Сестра", 2019, "Sister")
POOL = [FIRST, SECOND, STRANGER]


def test_a_subtitle_names_its_own_pictures() -> None:
    """Так работает запрос, который в карточке отвечает четырьмя картинами."""
    found = pick_franchise("Байки Мэтра", _pictures())

    assert [(p.title, p.year) for p in found] == [
        ("Тачки: Байки Мэтра", 2008),
        ("Тачки: Байки Мэтра", 2010),
    ]


def test_one_missing_letter_is_not_a_missing_picture() -> None:
    """🔴 TC-777. «Байки Мэтр» отказывал там, где «Байки Мэтра» давало картины."""
    assert [p.year for p in pick_franchise("Байки Мэтр", _pictures())] == [2008, 2010]


def test_the_year_from_our_own_menu_is_taken_back() -> None:
    """🔴 TC-777. Год мы печатаем сами - «(2008)», - и он обязан сужать, а не отказывать."""
    assert [p.year for p in pick_franchise("Байки Мэтра 2008", _pictures())] == [2008]


def test_a_year_nobody_has_leaves_the_pictures_of_the_name() -> None:
    """Год ошибиться может, а имя названо верно - отказывать по одному году не за что."""
    assert [p.year for p in pick_franchise("Байки Мэтра 1999", _pictures())] == [2008, 2010]


def test_a_name_the_catalogue_does_not_know_is_still_nothing() -> None:
    assert pick_franchise("хоббит", _pictures()) == []


def test_the_franchise_name_brings_the_whole_franchise_in_order() -> None:
    """Спросили франшизу - в меню идут все её части, и первая стоит первой."""
    assert [p.title for p in pick_franchise("Брат", POOL)] == ["Брат", "Брат 2"]


def test_a_number_in_the_query_names_one_part() -> None:
    """«Брат 2» - это одна картина: показывать после номера меню было бы лишним."""
    assert [p.title for p in pick_franchise("Брат 2", POOL)] == ["Брат 2"]


def test_the_original_name_leads_to_the_same_franchise() -> None:
    """Картину спрашивают латиницей, а найтись она обязана та же."""
    assert [p.title for p in pick_franchise("Brother", POOL)] == ["Брат", "Брат 2"]


def test_a_third_name_of_the_picture_leads_to_it_too() -> None:
    """Третьим именем картину зовут раздачи, и это тот же вход в неё."""
    pool = [_picture("Брат", 1997, aliases=("bratan",))]

    assert [p.title for p in pick_franchise("Bratan", pool)] == ["Брат"]


def test_a_query_the_catalogue_does_not_answer_gets_nothing() -> None:
    """Пустой ответ честнее подставленного соседа: включать не то нельзя."""
    assert pick_franchise("Матрица", POOL) == []


def test_a_typo_in_the_name_keeps_the_number_of_the_part() -> None:
    """🔴 TC-869. Описка правится в имени, а номер части названа зрителем верно.

    Имя каталога после прощения описки спрашивалось заново и голым, номер терялся, и по
    Enter вставала ПЕРВАЯ часть франшизы вместо названной второй. Отдать не ту часть под
    знакомым именем не лучше отказа.
    """
    pool = [
        _picture("Терминатор", 1984, "The Terminator"),
        _picture("Терминатор 2: Судный день", 1991, "Terminator 2", part=2),
    ]

    assert [p.title for p in pick_franchise("Тирминатор 2", pool)] == ["Терминатор 2: Судный день"]
    assert [p.title for p in pick_franchise("Тирминатор", pool)] == [
        "Терминатор",
        "Терминатор 2: Судный день",
    ]


def test_a_subtitle_named_by_a_piece_still_reaches_its_picture() -> None:
    """🔴 TC-967. Запрос подписью доставался однофамильцу с мёртвым роем, и только ему.

    Ключом группы стоит `love-me`: подпись отрезана двоеточием ещё в имени франшизы.
    Запрос «Kaede to Suzu» в этот ключ не входит вовсе, и никакой поиск по ключу до
    картины не достанет - доводит её только сличение подписи КУСКОМ. Снять его, и
    выдача по этому запросу становится пустой.

    🔴 TC-969. Раздача с украинской озвучкой стоит тут же и отдельным пунктом БОЛЬШЕ не
    встаёт: разводили её с остальными суффикс «The Animation» и голое «- 01» без
    скобочной группы, а работа это одна и та же. Живой рой и мёртвая раздача лежат
    теперь в одной картине, и выбирать между двумя строками меню человеку не нужно.
    """
    names = [
        "[SakuraCircle] Love Me: Kaede to Suzu The Animation - 01 (らぶみー 第1巻) - Softsubs",
        "[SakuraCircle] Love Me: Kaede to Suzu The Animation - 02 (らぶみー 第2巻) - Softsubs",
        "Love Me! Kaede to Suzu - 01 (UKR DVO)",
    ]
    pool = cluster([parse_release_name(name) for name in names])
    found = pick_franchise("Kaede to Suzu", pool)

    assert [p.title for p in found] == ["Love Me: Kaede to Suzu The Animation"]
    assert len(found[0].releases) == len(names)


def test_the_live_swarm_is_reached_through_the_bare_name() -> None:
    """🔴 TC-969. «У меня почти ничего не нашлось» при живом рое в сорок сидов.

    Выдача звала один сериал двумя именами, и по голому «Sakusei Byoutou» человек
    попадал в мёртвую однофамилицу, а рой оставался вне меню.

    Сторож стоит на ОБА конца сразу, и в этом весь смысл. Починить склейку мало: имена
    сойдутся, картина вберёт живой набор, а ключ франшизы слово удержит - и голый запрос
    по точному ключу уедет в соседнюю картину-фильм, у которой сидов нет. Починить один
    ключ тоже мало: картины останутся врозь. Красным этот тест становится и от того, и
    от другого отката.
    """
    names = [
        "[SakuraCircle] Sakusei Byoutou The Animation - 01 (搾精病棟) - English Softsubs",
        "[SakuraCircle] Sakusei Byoutou The Animation - 02 (搾精病棟) - English Softsubs",
        "[AmateurSubs] Sakusei Byoutou - 03 (English subs) [DVDRip 576p]",
        "[SourCream Subs] Sakusei Byoutou (Sectia de Extragere a Spermei) [1920x1080]",
    ]
    pool = cluster([parse_release_name(name) for name in names])
    found = pick_franchise("Sakusei Byoutou", pool)

    assert found[0].kind == "tv"
    assert len(found[0].releases) == 3


def test_one_bare_word_takes_the_heaviest_of_the_equally_near_franchises() -> None:
    """🔴 TC-1025. Голое слово: близость меряется ЛИШНИМИ СЛОВАМИ, а не буквами.

    Живая выдача RuTor по запросу «властелин» - 100 строк, среди них вся трилогия
    «Властелин колец». Отвечал же продукт ОДНОЙ чужой картиной «Властелин мира»
    (1961, 0 сид), и всё её преимущество было в том, что «мира» на одну букву короче
    «колец»: группы сортировались длиной слага.

    Обе группы дописывают к спрошенному слову ровно одно своё, то есть стоят от запроса
    одинаково далеко, и разводит их вес каталога - 48 раздач против двух.
    """
    names = [
        "Властелин Мира / Master of the World (1961) DVDRip| P2, A",
        "Властелин мира / Master of the World (1983) BDRemux 1080p",
        "Властелин колец: Братство кольца / The Lord of the Rings: The Fellowship of the Ring "
        "(2001) BDRip 1080p",
        "Властелин колец: Две крепости / The Lord of the Rings: The Two Towers (2002) BDRip 1080p",
        "Властелин колец: Возвращение короля / The Lord of the Rings: The Return of the King "
        "(2003) BDRip 1080p",
    ]
    pool = cluster([parse_release_name(name) for name in names])
    found = pick_franchise("властелин", pool)

    assert found, "по голому слову не нашлось ничего - а трилогия в выдаче есть"
    assert all("колец" in p.title for p in found), "выдача увела в чужую картину: " + ", ".join(
        f"{p.title} ({p.year})" for p in found
    )
    assert len(found) == 3


def test_a_lone_foreign_namesake_does_not_take_the_whole_query() -> None:
    """🔴 TC-1025, второй заход. Точное совпадение слага уходило ответом МИМО ранжирования.

    Замер на широком пуле стенда `.135`: 7 индексеров, 276 строк, 19 групп. Среди них
    есть группа со слагом РОВНО «властелин» - индийский «Sikandar Sadak Ka» (1999),
    выпущенный по-русски одним словом. Одна картина, одна раздача, - и она забирала
    запрос себе, не спросив ни близости, ни веса. На узком пуле `.50` этой раздачи в
    выдаче нет вовсе, поэтому гейт случая не видел, а смок сведённого master - увидел.
    """
    names = [
        "Властелин / Sikandar Sadak Ka (1999) WEB-DL 1080p",
        "Властелин колец: Братство кольца / The Lord of the Rings: The Fellowship of the Ring "
        "(2001) BDRip 1080p",
        "Властелин колец: Две крепости / The Lord of the Rings: The Two Towers (2002) BDRip 1080p",
        "Властелин колец: Возвращение короля / The Lord of the Rings: The Return of the King "
        "(2003) BDRip 1080p",
    ]
    pool = cluster([parse_release_name(name) for name in names])
    found = pick_franchise("властелин", pool)

    assert found, "по голому слову не нашлось ничего"
    assert all("колец" in p.title for p in found), (
        "запрос забрал тёзка в одну раздачу: " + ", ".join(f"{p.title} ({p.year})" for p in found)
    )


def test_a_third_name_does_not_hand_the_query_to_a_barely_known_picture() -> None:
    """🔴 «стражи»: псевдоним «Часовых» уводил запрос мимо «Стражей Галактики»."""
    names = [
        "Часовые / Les Sentinelles (2023) WEB-DL 1080p",
        "Стражи Галактики / Guardians of the Galaxy (2014) BDRip 1080p",
        "Стражи Галактики / Guardians of the Galaxy (2014) WEB-DL 2160p",
        "Стражи Галактики. Часть 2 / Guardians of the Galaxy Vol. 2 (2017) BDRip 1080p",
        "Стражи Галактики 3 / Guardians of the Galaxy Vol. 3 (2023) WEB-DL 1080p",
    ]
    pictures = cluster([parse_release_name(name) for name in names])
    pictures = [
        replace(picture, aliases=("стражи",)) if picture.title.startswith("Часовые") else picture
        for picture in pictures
    ]

    got = pick_franchise("стражи", pictures)

    assert got
    assert all("Стражи" in picture.title for picture in got), [p.title for p in got]


#: 🔴 TC-1064. Каталог двуязычен: у «Матрицы» русское название и оригинал в одной строке,
#: а у однофамильцев названия только латинские. Замер на стенде, запрос «matrix»: 68 картин,
#: и «Матрица» (58 раздач) не попадала в ответ вовсе - её группа зовётся «матрица», а
#: спрошенное слово подстрокой сидит в «the-animatrix».
_BILINGUAL = [
    "Матрица / The Matrix (1999) BDRip 1080p",
    "Матрица: Перезагрузка / The Matrix Reloaded (2003) BDRip 1080p",
    "The Animatrix (2003) BDRip 1080p",
    "L-MATRIX (2011) WEBRip 720p",
    "Slave Matrix (2018) WEBRip 720p",
]


def test_a_latin_word_reaches_the_picture_titled_in_the_other_language() -> None:
    """Неполное имя латиницей находит картину, которая этим словом называется."""
    pictures = cluster([parse_release_name(name) for name in _BILINGUAL])

    assert [p.title for p in pick_franchise("matrix", pictures)][:1] == ["Матрица"]


def test_a_latin_namesake_is_still_reachable_by_its_own_full_word() -> None:
    """Второе имя не съедает однофамильца: спрошенное «animatrix» остаётся своим."""
    pictures = cluster([parse_release_name(name) for name in _BILINGUAL])

    assert [p.title for p in pick_franchise("animatrix", pictures)] == ["The Animatrix"]


#: 🔴 TC-1064. Подзаголовок называет ОДНУ часть, а не франшизу. Замер на пуле стенда:
#: мост, взявший полные слаги оригиналов, растворял «towers» и «rohirrim» во весь
#: «Властелин колец» - слово из подзаголовка отвечало картине, которой в нём нет.
_SUBTITLED = [
    "Властелин колец: Братство кольца / The Lord of the Rings: The Fellowship of the Ring"
    " (2001) BDRip 1080p",
    "Властелин колец: Братство кольца / The Lord of the Rings: The Fellowship of the Ring"
    " (2001) BDRip 720p",
    "Властелин колец: Две крепости / The Lord of the Rings: The Two Towers (2002) BDRip 1080p",
]


def test_a_word_from_the_subtitle_answers_its_own_part_not_the_whole_franchise() -> None:
    """Мост во второе имя идёт по франшизному имени, а не по полному слагу оригинала."""
    pictures = cluster([parse_release_name(name) for name in _SUBTITLED])

    found = pick_franchise("towers", pictures)

    assert [p.title for p in found] == ["Властелин колец: Две крепости"]
