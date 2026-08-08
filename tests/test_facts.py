"""Справка к меню франшизы: матчинг статьи, разбор ответов и молчащий источник.

Фикстуры — обрезанные живые ответы ru.wikipedia и Wikidata на «тачки» и «моану»:
именно на них видно, ради чего проверка года вообще существует.
"""

from __future__ import annotations

import json
from typing import Any

from torrcast import cli
from torrcast import facts as facts_mod
from torrcast.facts import (
    BLURB_CAP,
    Fact,
    Facts,
    confirms,
    hms,
    ratings,
    read_sparql,
    sentence,
    shorten,
    titles_for,
    wiki_extracts,
)

CARS = (
    "«Та́чки» (англ. Cars) — американский компьютерно-анимационный спортивный комедийный "
    "фильм 2006 года, снятый студией Pixar для кинокомпании Walt Disney Pictures. "
    "Режиссёром выступил Джон Лассетер."
)
MOANA = (
    "«Моа́на» (англ. Moana) — американский компьютерно-анимационный музыкальный "
    "фэнтезийно-приключенческий фильм 2016 года, снятый студией Walt Disney Animation "
    "Studios и выпущенный студией Walt Disney Pictures."
)
MOANA_2026 = (
    "«Моа́на» (англ. Moana) — американский музыкальный фэнтезийно-приключенческий фильм "
    "режиссёра Томаса Кайла по сценарию Джареда Буша и Даны Леду Миллер."
)
DISAMBIG = "Моа́на переводится как море или океан с большинства полинезийских языков."


def _wiki_reply() -> dict[str, Any]:
    """Живой ответ ``action=query`` на пачку кандидатов по «моане» и «тачкам»."""
    return {
        "query": {
            "pages": [
                {"title": "Тачки", "extract": CARS, "pageprops": {"wikibase_item": "Q182153"}},
                {"title": "Моана", "extract": DISAMBIG, "pageprops": {"disambiguation": ""}},
                {
                    "title": "Моана (мультфильм)",
                    "extract": MOANA,
                    "pageprops": {"wikibase_item": "Q1183953"},
                },
                {
                    "title": "Моана (фильм, 2026)",
                    "extract": MOANA_2026,
                    "pageprops": {"wikibase_item": "Q107027107"},
                },
                {"title": "Моана 3", "missing": True},
            ]
        }
    }


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


def test_the_year_in_the_text_is_what_confirms_the_picture() -> None:
    """Единственная защита от чужого фильма — год в первых фразах статьи."""
    assert confirms(MOANA, 2016)
    assert not confirms(MOANA, 2026), "мультфильм 2016 года не выдать за ремейк"
    assert not confirms(MOANA_2026, 2026), "года в тексте нет - значит, подтвердить нечем"
    assert not confirms(CARS, None), "год картины неизвестен - сверять не с чем"


def test_a_disambiguation_page_is_not_a_description() -> None:
    """«Моана» голым именем — статья про полинезийское слово, а не про кино."""
    about, entities = facts_mod._read_pages(
        _wiki_reply(), {("Моана", 2016): titles_for("Моана", 2016)}
    )
    assert about[("Моана", 2016)] == MOANA
    assert entities[("Моана", 2016)] == "Q1183953"


def test_an_unconfirmed_picture_gets_nothing_rather_than_someones_else_film() -> None:
    """Ремейк 2026 года в тексте себя не называет — и справки у него не будет."""
    about, entities = facts_mod._read_pages(
        _wiki_reply(), {("Моана", 2026): titles_for("Моана", 2026)}
    )
    assert about == {}
    assert entities == {}


def test_redirects_lead_back_to_the_requested_name() -> None:
    """API нормализует имя и ведёт по перенаправлению — обратный путь читаем из ответа."""
    payload = {
        "query": {
            "normalized": [{"from": "тачки", "to": "Тачки"}],
            "redirects": [{"from": "Тачки", "to": "Тачки (мультфильм)"}],
            "pages": [
                {
                    "title": "Тачки (мультфильм)",
                    "extract": CARS,
                    "pageprops": {"wikibase_item": "Q182153"},
                }
            ],
        }
    }
    about, entities = facts_mod._read_pages(payload, {("тачки", 2006): ["тачки"]})
    assert about[("тачки", 2006)] == CARS
    assert entities[("тачки", 2006)] == "Q182153"


def test_sparql_gives_the_imdb_id_and_the_running_time() -> None:
    """Живой ответ Wikidata: у «Тачек» есть и то и другое, у страницы значений — ничего."""
    payload = {
        "results": {
            "bindings": [
                {
                    "item": {"value": "http://www.wikidata.org/entity/Q182153"},
                    "imdb": {"value": "tt0317219"},
                    "dur": {"value": "116"},
                },
                {"item": {"value": "http://www.wikidata.org/entity/Q1183953"}},
            ]
        }
    }
    assert read_sparql(payload) == {"Q182153": ("tt0317219", 116), "Q1183953": ("", 0)}


def test_running_time_reads_as_a_human_would_say_it() -> None:
    assert hms(116) == "1 ч 56 мин"
    assert hms(47) == "47 мин"
    assert hms(60) == "1 ч", "«1 ч 0 мин» так не говорят"
    assert hms(0) == ""


def test_the_description_is_the_whole_first_sentence() -> None:
    """Описание — первая фраза целиком: с жанром и годом, а не огрызок до многоточия."""
    assert shorten(CARS).endswith("Walt Disney Pictures.")
    assert "Режиссёром" not in shorten(CARS), "вторая фраза в меню не нужна"
    assert "..." not in shorten(CARS), "фраза влезла в потолок - резать нечего"


def test_only_a_sentence_past_the_cap_gets_an_ellipsis() -> None:
    """Многоточие остаётся ровно для фраз длиннее всякого разумного потолка."""
    long_one = "«Оппенгеймер» (англ. Oppenheimer) — " + "очень длинное описание, " * 20
    cut = shorten(long_one)
    assert len(cut) <= BLURB_CAP + 3 and cut.endswith("...")
    assert not cut.endswith(",..."), "хвост запятой перед многоточием не нужен"
    assert shorten("«Тачки» — мультфильм. Вторая фраза.", 10) == "«Тачки»..."


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


def test_ratings_come_from_the_offline_dump(tmp_path: Any) -> None:
    """Оценка читается из выгрузки IMDb, а нет файла — просто нет оценок."""
    dump = tmp_path / "imdb-ratings.tsv"
    dump.write_text("tconst\taverageRating\tnumVotes\ntt0317219\t7.3\t544373\n", encoding="utf-8")
    assert ratings(dump) == {"tt0317219": "7.3"}
    assert ratings(tmp_path / "нет-такого") == {}


def test_a_silent_source_leaves_the_menu_exactly_as_it_was(monkeypatch: Any) -> None:
    """Источник лёг — меню печатается прежней строкой и не ждёт ни секунды.

    Это и есть главное ограждение справки: она украшение, а не механизм показа.
    """

    def dead(*_a: Any, **_k: Any) -> Any:
        raise OSError("сети нет")

    monkeypatch.setattr(facts_mod, "fetch", dead)
    monkeypatch.setattr(facts_mod, "_cached", lambda wanted: {})
    facts = Facts([("Моана", 2016)], budget=0.5)
    facts.start()
    assert facts.get("Моана", 2016) == Fact()


def test_the_menu_never_waits_longer_than_its_budget(monkeypatch: Any) -> None:
    """Источник молчит (не отвечает вовсе) — меню уходит по бюджету, а не висит."""
    import time

    monkeypatch.setattr(facts_mod, "_cached", lambda wanted: {})

    def never(_wanted: Any) -> Any:
        time.sleep(30)
        return {}

    monkeypatch.setattr(facts_mod, "fetch", never)
    facts = Facts([("Моана", 2016)], budget=0.3)
    facts.start()
    started = time.monotonic()
    assert facts.get("Моана", 2016) == Fact()
    assert time.monotonic() - started < 3.0


def test_menu_prints_the_old_line_when_there_is_no_help() -> None:
    """Без справки меню — ровно тот же список, что и до неё."""
    from tests.test_cli import _moana_franchise

    plans = _moana_franchise()
    assert cli.menu_lines(plans, None, width=80) == (
        "  1. Моана: романтика золотого века (1926)\n  2. Моана (2016)\n  3. Моана 2 (2024)"
    )


def test_menu_puts_rating_and_time_in_the_head_and_the_plot_below() -> None:
    """Со справкой: рейтинг с источником и хронометраж в строке названия, описание — под."""
    from tests.test_cli import _moana_franchise

    plans = _moana_franchise()
    facts = Facts([])
    facts.start()
    facts.found = {("Моана", 2016): Fact(about=MOANA, rating="IMDb 7.6", runtime="1 ч 47 мин")}
    printed = cli.menu_lines(plans, facts, width=80).splitlines()
    assert printed[0] == "  1. Моана: романтика золотого века (1926)"
    assert printed[1] == "  2. Моана (2016) · IMDb 7.6 · 1 ч 47 мин"
    assert printed[2].startswith("     «Моа́на» (англ. Moana) — американский")
    assert printed[-1] == "  3. Моана 2 (2024)", "у остальных справки нет - и лишних строк нет"


def test_the_description_wraps_by_words_under_the_terminal() -> None:
    """Описание переносится по словам, каждая строка — с тем же отступом и в ширину."""
    from tests.test_cli import _moana_franchise

    facts = Facts([])
    facts.start()
    facts.found = {("Моана", 2016): Fact(about=MOANA)}
    printed = cli.menu_lines(_moana_franchise(), facts, width=60).splitlines()
    blurb = [line for line in printed if line.startswith("     ")]
    assert len(blurb) > 1, "фраза не влезла в одну строку - значит, перенеслась"
    assert all(len(line) < 60 for line in blurb), "строка не должна вылезать за терминал"
    assert not any(line.endswith("-") for line in blurb), "перенос по словам, не по дефису"
    assert " ".join(line.strip() for line in blurb) == MOANA, "фраза цела и ничем не обрезана"


def test_one_request_carries_the_whole_franchise(monkeypatch: Any) -> None:
    """Все картины и все кандидаты уезжают одним запросом — их не по одному тянуть."""
    calls: list[dict[str, str]] = []

    def get(host: str, path: str, params: dict[str, str], headers: dict[str, str],
            timeout: float) -> Any:  # fmt: skip
        calls.append(params)
        return _wiki_reply()

    monkeypatch.setattr(facts_mod, "get_json", get)
    about, _ = wiki_extracts([("Тачки", 2006), ("Моана", 2016)], 1.0)
    assert len(calls) == 1
    titles = calls[0]["titles"].split("|")
    assert titles[0] == "Тачки" and titles[1] == "Моана", "по кандидату на картину, потом вглубь"
    assert len(titles) <= 20, "лимит API на статьи в одном запросе"
    assert about[("Тачки", 2006)] == CARS
    assert about[("Моана", 2016)] == MOANA


def test_broken_cache_is_the_same_as_no_cache(tmp_path: Any, monkeypatch: Any) -> None:
    """Битый кэш не роняет меню и не подсовывает мусор."""
    path = tmp_path / "facts.json"
    path.write_text("{не json", encoding="utf-8")
    monkeypatch.setattr(facts_mod, "CACHE_PATH", path)
    assert facts_mod._cached([("Моана", 2016)]) == {}
    path.write_text(json.dumps({"Моана|2016": {"rating": "IMDb 7.6"}}), encoding="utf-8")
    assert facts_mod._cached([("Моана", 2016)]) == {("Моана", 2016): Fact(rating="IMDb 7.6")}


WEDNESDAY = (
    "«Уэ́нздей» (англ. Wednesday) — американский комедийный сверхъестественный телесериал, "
    "созданный Альфредом Гофом и Майлзом Милларом для стримингового сервиса Netflix."
)
UTENA = (
    "«Юная революционерка Утэна» (яп. 少女革命ウテナ) — аниме-сериал, выпущенный студией "
    "J.C.Staff под руководством режиссёра Кунихико Икухары."
)
CLIMBERS = "«Восхождение» (англ. The Climbers) — китайский фильм 2019 года режиссёра Дэниела Ли."
#: Тип картины описательный: ни «фильма», ни «сериала» в статье нет вовсе.
BREAKING_BAD = (
    "«Во все тяжкие» (англ. Breaking Bad) — американская телевизионная криминальная драма, "
    "премьерные серии которой транслировались с 20 января 2008 года по 29 сентября 2013 "
    "года по кабельному каналу AMC.\nНа протяжении пяти сезонов, состоящих из 62 эпизодов, "
    "показана история Уолтера Уайта, школьного учителя, у которого диагностировали "
    "неоперабельный рак лёгких."
)
#: Не кино. Все семь - живые начала статей ru.wikipedia, и у каждой есть скобка с
#: латиницей либо латинский заголовок, то есть :func:`~torrcast.facts.latin_title` найдёт
#: в ней «оригинал», если её пустить дальше гейта.
NOT_CINEMA = {
    "Питт, Брэд": (
        "Уи́льям Брэ́дли Питт (англ. William Bradley Pitt; род. 18 декабря 1963, Шони, "
        "Оклахома, США) — американский актёр и кинопродюсер. Лауреат двух «Оскаров», двух "
        "BAFTA, двух «Золотых глобусов» и одной «Эмми»."
    ),
    "Уотсон, Эмма": (
        "Э́мма Шарло́тта Дюэ́рр Уо́тсон (англ. Emma Charlotte Duerre Watson; род. 15 апреля "
        "1990, Мезон-Лаффит, пригород Парижа, Франция) — британская киноактриса и "
        "фотомодель.\nПолучила широкую известность благодаря роли Гермионы Грейнджер в "
        "фильмах о Гарри Поттере, в которых снималась вместе с Дэниелом Рэдклиффом."
    ),
    "Пол, Аарон": (
        "Аа́рон Пол Сте́ртевант (англ. Aaron Paul Sturtevant; род. 27 августа 1979) — "
        "американский актёр. Наиболее известен как исполнитель роли Джесси Пинкмана в "
        "сериале «Во все тяжкие», за участие в котором Пол получил три премии «Эмми» в "
        "категории «Лучший актёр второго плана в драматическом телесериале»."
    ),
    "Новосибирск": (
        "Новосиби́рск (МФА: nəvəsʲɪˈbʲirsk ; до 1926 года — Но́во-Никола́евск) — третий по "
        "численности населения город России, крупнейший город её азиатской части, "
        "административный центр Новосибирской области."
    ),
    "NBC": (
        "Национа́льная широковеща́тельная компа́ния, сокр. «Эн-би-си́» (англ. National "
        "Broadcasting Company, сокр. NBC) — американская коммерческая телекомпания (в "
        "прошлом телерадиокомпания) и принадлежащая ей телевизионная сеть."
    ),
    "Netflix": (
        "Netflix, Inc. — американская развлекательная компания и стриминговый сервис "
        "фильмов и сериалов. Основана 29 августа 1997 года Ридом Хастингсом и Марком "
        "Рэндольфом.\nС 2013 года Netflix производит собственные фильмы и сериалы, в том "
        "числе и анимационные, а также телепрограммы."
    ),
    "Дюна (роман)": (
        "«Дю́на» (англ. Dune) — эпический научно-фантастический роман американского "
        "писателя Фрэнка Герберта, впервые опубликованный в 1963—1965 годах в виде серии "
        "глав в журнале Analog Science Fiction and Fact и в 1965 году впервые изданный "
        "отдельной книгой."
    ),
}


def _page(heading: str, extract: str, english: str = "") -> dict[str, Any]:
    """Статья в том виде, в каком её отдаёт ``action=query``."""
    page: dict[str, Any] = {"title": heading, "extract": extract}
    if english:
        page["langlinks"] = [{"lang": "en", "title": english}]
    return page


def test_wikipedia_knows_better_than_us_how_the_asked_name_is_spelled() -> None:
    """Имя назвали мы сами, до статьи довело перенаправление - спорить с ним нечем.

    «Уэнсдей» в русской Википедии пишется «Уэнздей», и прежняя сверка заголовка
    (:func:`~torrcast.facts.akin`) отвергала статью, которую сама же Википедия и выдала:
    справка молчала ровно там, где знала ответ, и поиску нечем было добирать.
    """
    page = _page("Уэнздей", WEDNESDAY)

    assert facts_mod.read_origin([page], "Уэнсдей", trusted=True).title == "Wednesday"


def test_a_namesake_from_the_search_is_still_checked_by_its_heading() -> None:
    """Послабление касается только имён, которые мы назвали сами.

    Поиск Википедии приносит однофамильцев наравне с нужным, и «Восхождение» 2019 года
    под запрос «Восхождение» не подходит только заголовком - сверка остаётся.
    """
    page = _page("Ганнибал: Восхождение", CLIMBERS)

    assert not facts_mod.read_origin([page], "Восхождение")
    assert facts_mod.read_origin([page], "Ганнибал: Восхождение").year == 2019


def test_a_picture_whose_type_is_spelled_out_still_gives_up_its_original_name() -> None:
    """Тип картины бывает описательным - оригинал от этого никуда не девается.

    Статья о «Во все тяжкие» открывается словами «американская телевизионная криминальная
    драма»: слов «фильм» и «сериал» в ней нет ни одного, и справка молчала на ровном месте.
    А оригинал (Breaking Bad) стоит там же, где у всех - в первой скобке, и он нужен
    поиску: без него у картины остаётся одно имя из двух.
    """
    page = _page("Во все тяжкие", BREAKING_BAD)

    found = facts_mod.read_origin([page], "Во все тяжкие", trusted=True)
    assert found.title == "Breaking Bad"
    assert found.year == 2008
    assert found.name == "Во все тяжкие"
    # Поиском Википедии - тот же ответ: заголовок статьи под запрос подходит.
    assert facts_mod.read_origin([page], "Во все тяжкие").title == "Breaking Bad"


def test_an_article_that_is_not_about_cinema_gives_nothing_at_all() -> None:
    """Главное ограждение: человек, город, компания и книга паспорта не получают.

    Скобка с латиницей есть у кого угодно - «(англ. William Bradley Pitt)», «(англ. Dune)»
    у романа Герберта, - и стоит пустить такую статью дальше гейта, как справка молча
    выдаст чужую строку за оригинальное название картины. Это худший из возможных ответов:
    поиск уйдёт добирать не ту картину, и человек этого не увидит.

    Проверка идёт с ``trusted=True`` намеренно: там сверки заголовка нет вовсе
    (:func:`~torrcast.facts.akin` не зовётся), и держит ответ пустым ровно этот гейт.
    """
    for heading, extract in NOT_CINEMA.items():
        page = _page(heading, extract, english=heading)
        asked = heading.split(" (")[0]

        assert not facts_mod.read_origin([page], asked, trusted=True), heading
        assert not facts_mod.read_origin([page], asked), heading


def test_the_original_name_comes_from_the_english_article_when_the_text_has_none() -> None:
    """У аниме в скобке иероглифы, а не латиница - имя берётся из английской статьи."""
    page = _page("Юная революционерка Утэна", UTENA, english="Revolutionary Girl Utena")

    found = facts_mod.read_origin([page], "Утэна", trusted=True)
    assert found.title == "Revolutionary Girl Utena"


def test_the_english_heading_loses_its_disambiguation_bracket() -> None:
    """«Wednesday (TV series)» - это разметка Википедии; индексер ищет «Wednesday»."""
    assert facts_mod.english_title(_page("Уэнздей", "", english="Wednesday (TV series)")) == (
        "Wednesday"
    )
    assert facts_mod.english_title(_page("Тачки", "", english="Cars (film)")) == "Cars"
    assert facts_mod.english_title(_page("Внутри Лапенко", "")) == ""


def test_the_english_article_does_not_outrank_the_original_in_the_text() -> None:
    """Скобка первой фразы точнее: там оригинал, а не английское прокатное имя."""
    page = _page("Уэнздей", WEDNESDAY, english="Wednesday (TV series)")

    assert facts_mod.read_origin([page], "Уэнсдей", trusted=True).title == "Wednesday"


def test_the_english_link_rides_along_with_the_extracts() -> None:
    """Ссылка на английскую статью не стоит отдельного запроса - едет тем же."""
    params = facts_mod._extract_params(["Уэнздей"])

    assert "langlinks" in params["prop"]
    assert params["lllang"] == "en"
    assert int(params["lllimit"]) > 1, "потолок общий на все статьи запроса, не на первую"


def test_a_slash_inside_the_heading_does_not_make_it_another_picture() -> None:
    """«ВандаВижн» в русской Википедии подписан «Ванда/Вижн» - это то же имя."""
    assert facts_mod.akin("вандавижн", "Ванда/Вижн")
    assert facts_mod.akin("ВандаВижн", "Ванда/Вижн")
    # Склейка разделителей не должна открывать дорогу однофамильцу.
    assert not facts_mod.akin("восхождение", "Ганнибал: Восхождение")


def test_an_empty_answer_is_remembered_so_the_walk_is_not_repeated(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """Источник ответил, а сказать ему нечего - это тоже ответ, и он помнится.

    Раньше пустой ряд в кэш не попадал вовсе: каждое меню шло за ним в сеть заново, не
    успевало к дедлайну и печаталось голым - и следующее ровно так же.
    """
    monkeypatch.setattr(facts_mod, "CACHE_PATH", tmp_path / "facts.json")
    walks: list[Any] = []

    def once(wanted: Any, timeout: float = 0.0) -> Any:
        walks.append(list(wanted))
        return {("Тачки", 2006): Fact(rating="IMDb 7.2")}

    monkeypatch.setattr(facts_mod, "fetch", once)
    wanted = [("Тачки", 2006), ("Тачки: Мультачки. Байки Мэтра", 2008)]

    first = Facts(wanted, budget=5.0)
    first.start()
    assert first.get("Тачки", 2006).rating == "IMDb 7.2"
    first.finish()

    second = Facts(wanted, budget=5.0)
    second.start()
    assert second.get("Тачки", 2006).rating == "IMDb 7.2"
    assert second.get("Тачки: Мультачки. Байки Мэтра", 2008) == Fact()
    # Второй заход в сеть не пошёл: пустота лежит в кэше наравне с найденным.
    assert len(walks) == 1


def test_a_stale_empty_answer_is_asked_again(monkeypatch: Any, tmp_path: Any) -> None:
    """Срок у пустоты конечный: статью могли и написать - через :data:`EMPTY_TTL` спросим."""
    import time

    monkeypatch.setattr(facts_mod, "CACHE_PATH", tmp_path / "facts.json")
    stale = int(time.time()) - facts_mod.EMPTY_TTL - 1
    (tmp_path / "facts.json").write_text(
        json.dumps({"Моана|2016": {"about": "", "rating": "", "runtime": "", "empty": stale}}),
        encoding="utf-8",
    )
    walks: list[Any] = []

    def once(wanted: Any, timeout: float = 0.0) -> Any:
        walks.append(list(wanted))
        return {("Моана", 2016): Fact(about=MOANA)}

    monkeypatch.setattr(facts_mod, "fetch", once)
    facts = Facts([("Моана", 2016)], budget=5.0)
    facts.start()

    assert facts.get("Моана", 2016).about == MOANA
    assert walks == [[("Моана", 2016)]]


def test_the_network_answer_does_not_throw_away_what_the_cache_had(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """Сеть отвечает про ненайденное - и не вправе стирать уже найденное.

    Присваиванием ``self.found = fetch(...)`` кэшированная справка выбрасывалась: в меню
    из четырёх картин оставалась ровно та, про которую ответила сеть.
    """
    monkeypatch.setattr(facts_mod, "CACHE_PATH", tmp_path / "facts.json")
    monkeypatch.setattr(
        facts_mod, "_cached", lambda wanted: {("Тачки", 2006): Fact(rating="IMDb 7.2")}
    )
    monkeypatch.setattr(
        facts_mod, "fetch", lambda wanted, timeout=0.0: {("Тачки 2", 2011): Fact(rating="IMDb 6.2")}
    )
    facts = Facts([("Тачки", 2006), ("Тачки 2", 2011)], budget=5.0)
    facts.start()
    facts.finish()

    assert facts.get("Тачки", 2006).rating == "IMDb 7.2"
    assert facts.get("Тачки 2", 2011).rating == "IMDb 6.2"


def test_the_ratings_dump_is_read_alongside_the_first_request_not_after_it(
    monkeypatch: Any,
) -> None:
    """Выгрузка рейтингов - файл, а не сеть: внутри дедлайна она идёт параллельно запросу.

    Третьим шагом её сотня тысяч строк ложилась на те же полторы секунды, что и оба
    запроса, и справка не успевала к меню на ровном месте.
    """
    import time

    order: list[str] = []

    def slow_ratings() -> dict[str, str]:
        order.append("рейтинги-начало")
        time.sleep(0.3)
        order.append("рейтинги-конец")
        return {"tt0317219": "7.2"}

    def slow_wiki(wanted: Any, timeout: float) -> Any:
        order.append("вики-начало")
        time.sleep(0.3)
        order.append("вики-конец")
        return {("Тачки", 2006): CARS}, {("Тачки", 2006): "Q182153"}

    monkeypatch.setattr(facts_mod, "ratings", slow_ratings)
    monkeypatch.setattr(facts_mod, "wiki_extracts", slow_wiki)
    monkeypatch.setattr(
        facts_mod, "wikidata_ids", lambda items, timeout: {"Q182153": ("tt0317219", 117)}
    )

    started = time.monotonic()
    out = facts_mod.fetch([("Тачки", 2006)], timeout=5.0)
    spent = time.monotonic() - started

    assert out[("Тачки", 2006)].rating == "IMDb 7.2"
    # Оба шага стартовали до того, как кончился любой из них - значит шли вместе.
    assert order[:2] == ["рейтинги-начало", "вики-начало"]
    assert spent < 0.55


def test_a_memoized_address_rides_over_a_dns_storm(monkeypatch: Any) -> None:
    """Разрешённый адрес переживает DNS-бурю мимо резолвера, а голый getaddrinfo в ней тонет.

    ``socket.getaddrinfo`` таймауту сокета не подчиняется: под бурей параллельных
    резолвов прогрева он залипает дольше всего бюджета справки, и та не приезжает вовсе.
    Буря смоделирована блокирующим резолвером (``blocked`` не взведён - getaddrinfo не
    возвращается). Прямой резолв в ней не укладывается в бюджет, а память :func:`_resolve`
    и её собственный таймаут - укладываются.
    """
    import socket
    import threading
    import time

    from torrcast.facts import FACTS_BUDGET

    blocked = threading.Event()

    def stuck(host: str, *_a: Any, **_k: Any) -> Any:
        blocked.wait()  # под бурей резолвер не отвечает
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0))]

    monkeypatch.setattr("torrcast.facts.socket.getaddrinfo", stuck)
    facts_mod._RESOLVED.clear()

    # Память переживает бурю: адрес разрешили ОДНАЖДЫ, до бури.
    blocked.set()
    assert facts_mod._resolve("wiki.example", 1.0) == "1.2.3.4"
    blocked.clear()  # буря снова накрыла резолвер
    started = time.monotonic()
    assert facts_mod._resolve("wiki.example", 1.5) == "1.2.3.4"
    assert time.monotonic() - started < FACTS_BUDGET, "из памяти - мимо бури, в срок"

    # Холодный резолв под бурей не ест весь бюджет, а падает по своему таймауту.
    facts_mod._RESOLVED.clear()
    started = time.monotonic()
    try:
        facts_mod._resolve("cold.example", 0.5)
    except OSError:
        pass
    else:
        raise AssertionError("холодный резолв под бурей обязан упасть по таймауту")
    assert 0.5 <= time.monotonic() - started < 1.2, "уложился в свой таймаут, а не завис"

    # А вот голый getaddrinfo (прежнее поведение connect) в той же буре в срок не отвечает.
    done = threading.Event()

    def bare_resolve() -> None:
        socket.getaddrinfo("nomemo.example", 443)
        done.set()

    threading.Thread(target=bare_resolve, daemon=True).start()
    assert not done.wait(FACTS_BUDGET), "прямой getaddrinfo под бурей за бюджет не разрешился"

    blocked.set()  # отпустить залипших демонов
    facts_mod._RESOLVED.clear()


def test_an_unknown_type_is_trusted_only_when_film_and_series_agree(monkeypatch: Any) -> None:
    """Тип неизвестен (пустая выдача) - пробуем оба, но верим лишь согласию.

    Спека требует подсказывать тип, а на пустой выдаче его взять неоткуда. Наугад нельзя:
    неверный тип уводит в чужую статью. Поэтому при ``series=None`` справка спрашивает и
    фильм, и сериал, и берёт ответ, только если это одна картина.
    """
    from torrcast.facts import Origin, origin_either

    monkeypatch.setattr(facts_mod, "_cached_origin", lambda title, series: None)
    monkeypatch.setattr(facts_mod, "_remember_origin", lambda *a: None)

    def deadwood(title: str, series: bool, timeout: float) -> Origin:
        # Фильм 2006 против сериала 2004 - это разные картины, наугад не выдаём.
        if series:
            return Origin(title="Deadwood", year=2004, name="Дедвуд")
        return Origin(title="Deadwood: The Movie", year=2006, name="Дедвуд")

    monkeypatch.setattr(facts_mod, "origin_now", deadwood)
    assert origin_either("Дедвуд") == Origin(), "фильм и сериал разошлись - молчим"

    def climbers(title: str, series: bool, timeout: float) -> Origin:
        # С неверным типом «Восхождение» уводит в чужой сериал «Hunyadi» 2024.
        if series:
            return Origin(title="Hunyadi", year=2024, name="Восхождение ворона")
        return Origin(title="The Ascent", year=1976, name="Восхождение")

    monkeypatch.setattr(facts_mod, "origin_now", climbers)
    assert origin_either("Восхождение") == Origin(), "чужая статья из неверного типа - не паспорт"

    def agreeing(title: str, series: bool, timeout: float) -> Origin:
        return Origin(title="Cars", year=2006, name="Тачки")

    monkeypatch.setattr(facts_mod, "origin_now", agreeing)
    assert origin_either("Тачки").title == "Cars", "оба сошлись на одной картине - паспорт есть"

    def only_movie(title: str, series: bool, timeout: float) -> Origin:
        return Origin() if series else Origin(title="Psycho", year=1960, name="Психо")

    monkeypatch.setattr(facts_mod, "origin_now", only_movie)
    assert origin_either("Психо").title == "Psycho", "тип нашёлся один - его и берём"
