"""Справка к меню франшизы: матчинг статьи, разбор ответов и молчащий источник.

Фикстуры — обрезанные живые ответы ru.wikipedia и Wikidata на «тачки» и «моану»:
именно на них видно, ради чего проверка года вообще существует.
"""

from __future__ import annotations

import json
import time
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
#: Экранизация под именем сериала: игровой фильм 2015 года по манге «Атака на титанов».
#: Статьи «Атака титанов (телесериал)» в русской Википедии нет, и перебор уточнений
#: спокойно доходил сюда - на запрос про аниме-сериал справка отвечала этой картиной.
#: Заодно тут двуязычная скобка, латиница в которой перемешана с иероглифами.
ATTACK_FILM = (
    "«Атака титанов» (яп. 進撃の巨人) — японский художественный фильм, выпущенный на "
    "основе манги Хадзимэ Исаямы «Атака на титанов». Фильм разделён на две части, первая "
    "часть выпущена в Японии 1 августа 2015 года, а вторая часть под названием «Атака "
    "титанов: Конец света» (яп. 進撃の巨人 エンド オブ ザ ワールド Shingeki no Kyojin: Endo obu "
    "za Wārudo) — 19 сентября 2015 года."
)
#: Сериал 2014 года, который второй фразой рассказывает про фильм 1996-го.
FARGO_SERIES = (
    "«Фа́рго» (англ. Fargo) — американский телесериал-антология в жанре чёрной "
    "трагикомедии, создателем и автором которого является Ной Хоули. Проект вдохновлён "
    "одноимённым фильмом братьев Коэн 1996 года, которые выступили исполнительными "
    "продюсерами сериала. Премьера состоялась 15 апреля 2014 года на канале FX."
)
#: Год назван во всей врезке ровно один раз - спутать его не с чем.
MASTER_2005 = (
    "«Ма́стер и Маргари́та» — российский телесериал режиссёра Владимира Бортко по "
    "одноимённому роману Михаила Булгакова.\nПремьера состоялась 19 декабря 2005 года на "
    "телеканале «Россия» показом первых двух серий."
)
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


def test_a_film_does_not_answer_for_the_series_it_was_made_from() -> None:
    """Худший брак справки: спросили сериал, а она уверенно назвала его экранизацию.

    «Атака титанов» - японский аниме-сериал, но статьи «Атака титанов (телесериал)» в
    русской Википедии нет вовсе, и перебор уточнений доходил до «Атака титанов (фильм)» -
    игрового фильма 2015 года. Дальше не спасало ничто: статья про кино, заголовок под
    запрос подходит слово в слово, а год справке не подсказывают. Паспорт чужой картины
    уходил в гейт добора, где он сильнее выдачи, - и подмену никто не видел.

    Проверка с ``trusted=True``: это прямая выборка по имени, там сверки заголовка нет
    вовсе, и держать ответ пустым обязан гейт типа.
    """
    page = _page("Атака титанов (фильм)", ATTACK_FILM, english="Attack on Titan")

    assert not facts_mod.read_origin([page], "атака титанов", trusted=True, series=True)
    assert not facts_mod.read_origin([page], "атака титанов", series=True)
    # Спросили фильм - фильм и получите: гейт разводит типы, а не запрещает картину.
    found = facts_mod.read_origin([page], "атака титанов", trusted=True, series=False)
    assert found.title == "Attack on Titan"
    assert found.year == 2015


def test_the_original_name_is_never_a_string_of_hieroglyphs() -> None:
    """У японского кино скобка двуязычна, и латиница в ней - ещё не название.

    «(яп. 進撃の巨人 エンド オブ ザ ワールド Shingeki no Kyojin: Endo obu za Wārudo)» проходило
    прежнюю проверку («латиница есть, кириллицы нет») целиком, вместе с иероглифами, и
    ровно этой строкой поиск шёл добирать раздачу. Искать по ней нечего.
    """
    assert facts_mod.latin_title(ATTACK_FILM) == ""
    # Имя есть, просто лежит оно в английской статье.
    page = _page("Атака титанов (фильм)", ATTACK_FILM, english="Attack on Titan")
    assert facts_mod.read_origin([page], "атака титанов", trusted=True).title == "Attack on Titan"


def test_a_type_the_article_never_names_does_not_silence_it() -> None:
    """Гейт типа отказывает на противоречии, а не на молчании.

    «Во все тяжкие» открывается словами «американская телевизионная криминальная драма»:
    слова «сериал» там нет. Требуй гейт явного слова - справка замолчала бы на картинах,
    которые сегодня знает, а это тот самый случай, ради которого заведён :func:`_about_
    cinema`. Зато обратный вопрос («это фильм?») статья опровергает сама.
    """
    page = _page("Во все тяжкие", BREAKING_BAD)

    assert facts_mod.read_origin([page], "Во все тяжкие", trusted=True, series=True).year == 2008
    assert not facts_mod.read_origin([page], "Во все тяжкие", trusted=True, series=False)
    # Тип неизвестен - сверять нечем, и гейт молчит: так ходит origin_either.
    assert facts_mod.read_origin([page], "Во все тяжкие", trusted=True, series=None).year == 2008


def test_the_year_of_a_neighbour_in_the_franchise_is_not_this_pictures_year() -> None:
    """Год паспорта сильнее выдачи, поэтому чужой год - это та же подмена картины.

    Брался он первым попавшимся «NNNN года» по всей врезке, а в статьях об экранизациях
    это через раз год соседа: сериал «Фарго» 2014 года второй фразой сообщает, что
    «вдохновлён фильмом 1996 года», - и справка называла 1996.
    """
    page = _page("Фарго (телесериал)", FARGO_SERIES, english="Fargo")

    found = facts_mod.read_origin([page], "фарго", trusted=True, series=True)
    assert found.title == "Fargo", "саму картину справка по-прежнему знает"
    assert found.year is None, "1996 - год фильма, а не этого сериала"


def test_a_year_named_only_once_is_still_trusted() -> None:
    """Молчать в ответ на любой год - перебор: спутать единственный год не с чем.

    У «Мастера и Маргариты» паспортная фраза года не называет вовсе, но во всей врезке он
    один - 2005. Отказ от него стоил бы гейту добора умения отличать сериал 2005 года от
    фильма 2024-го, а это ровно то, ради чего год и спрашивают.
    """
    assert facts_mod.picture_year(MASTER_2005) == 2005
    # Названо несколько - выбирать между ними нечем.
    assert facts_mod.picture_year(FARGO_SERIES) is None
    # Паспортная фраза сильнее всего остального.
    assert facts_mod.picture_year(CARS) == 2006
    assert facts_mod.picture_year(CLIMBERS) == 2019


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
    lone = origin_either("Психо")
    assert lone.title == "Psycho", "тип нашёлся один - имя его и берём"
    assert lone.year is None, "а год у одинокого ответа неподтверждён - см. соседний тест"


def test_a_lone_answer_lends_its_name_but_never_its_year(monkeypatch: Any) -> None:
    """Ответил один путь из двух - это не согласие, а единственное мнение. Год ему не верим.

    «Атака титанов»: статьи об аниме-сериале в русской Википедии нет вовсе, и на оба
    вопроса приезжает одна и та же статья японского игрового фильма. Гейт типа
    (:func:`~torrcast.facts._fits_type`) отдаёт её только вопросу про фильм, вопрос про
    сериал остаётся без ответа - и прежнее правило «ответил один - его и берём» уверенно
    подписывало аниме-сериал 2013 года чужим годом 2015.

    Имя и год у такого ответа стоят разного, поэтому и судьба у них разная. Имя ``Attack
    on Titan`` у фильма и сериала общее, добору оно годится, а ошибись оно - цена лишние
    раздачи. Год объявлен сильнее выдачи: с ним гейт добора выкидывает из каталога весь
    сериал 2013 года как «другую картину» - молча и уверенно. Отдаём имя, молчим про год.
    """
    from torrcast.facts import Origin, origin_either

    monkeypatch.setattr(facts_mod, "_cached_origin", lambda title, series: None)
    monkeypatch.setattr(facts_mod, "_remember_origin", lambda *a: None)
    film = _page("Атака титанов (фильм)", ATTACK_FILM, english="Attack on Titan")

    def wiki(title: str, series: bool, timeout: float) -> Origin:
        return facts_mod.read_origin([film], title, trusted=True, series=series)

    monkeypatch.setattr(facts_mod, "origin_now", wiki)

    # Так эта статья отвечает каждому из двух путей: фильму - всё, сериалу - ничего.
    assert wiki("Атака титанов", False, 1.0) == Origin("Attack on Titan", 2015, "Атака титанов")
    assert not wiki("Атака титанов", True, 1.0), "чужой тип - гейт молчит (соседняя работа)"

    lone = origin_either("Атака титанов")
    assert lone.title == "Attack on Titan", "имя общее у фильма и сериала - добору годится"
    assert lone.name == "Атака титанов", "русское имя тоже: по нему добор ищет обратно"
    assert lone.year is None, "год у сериала 2013, а не 2015 - неподтверждённый год не отдаём"


def test_the_publication_year_is_the_earliest_p577_date() -> None:
    """🔴 TC-134. Год первой публикации из P577 - самая ранняя дата; ни одной - ``None``."""
    payload = {
        "results": {
            "bindings": [
                {"date": {"value": "2016-12-02T00:00:00Z"}},  # прокат в одной стране
                {"date": {"value": "2016-11-14T00:00:00Z"}},  # премьера - раньше
            ]
        }
    }
    assert facts_mod.read_published(payload) == 2016
    assert facts_mod.read_published({"results": {"bindings": []}}) is None
    assert facts_mod.read_published("не словарь") is None


def test_a_lone_year_is_kept_only_when_a_second_source_confirms_it(monkeypatch: Any) -> None:
    """🔴 TC-134. Одинокий год отдаём, лишь если его подтверждает P577; иначе - только имя.

    Прежде год у одинокого ответа (:func:`origin_either`) отбирался ВСЕГДА, и с ним у
    верных одиночек терялась год-опора гейтов добора. Второй источник - дата первой
    публикации Wikidata (P577): совпала с годом статьи - год двух источников отдаём,
    разошлась или Wikidata молчит - МОЛЧИМ (только имя), а не выбираем «поудачнее».

    Таблица: имя -> (год статьи, P577) -> итог года.
    """
    from torrcast.facts import Origin, origin_either

    monkeypatch.setattr(facts_mod, "_cached_origin", lambda title, series: None)
    monkeypatch.setattr(facts_mod, "_remember_origin", lambda *a: None)
    p577 = {"Q1": 1960, "Q2": 2016, "Q3": 2008, "Q4": 1999, "Q5": None}
    monkeypatch.setattr(facts_mod, "published_year", lambda entity, timeout=1.0: p577.get(entity))

    # имя -> (паспорт статьи с Q-идентификатором, ожидаемый год итога)
    table = {
        "Психо": (Origin("Psycho", 1960, "Психо", "Q1"), 1960),  # 1960 == 1960 -> год
        "Моана": (Origin("Moana", 2016, "Моана", "Q2"), 2016),  # 2016 == 2016 -> год
        "Во все тяжкие": (Origin("Breaking Bad", 2008, "Во все тяжкие", "Q3"), 2008),  # -> год
        "Оно": (Origin("It", 2014, "Оно", "Q4"), None),  # P577 1999 != 2014 -> молчим
        "Медведь": (Origin("The Bear", 2026, "Медведь", "Q5"), None),  # Wikidata молчит -> молчим
    }
    for name, (paper, want) in table.items():
        monkeypatch.setattr(
            facts_mod,
            "origin_now",
            lambda title, series, timeout, paper=paper: Origin() if series else paper,
        )
        got = origin_either(name)
        assert got.title == paper.title, f"{name}: имя одинокого ответа остаётся всегда"
        assert got.year == want, f"{name}: год статьи {paper.year}, P577 {p577[paper.entity]}"


def test_a_lone_answer_without_a_wikidata_id_never_asks_for_a_second_source(
    monkeypatch: Any,
) -> None:
    """🔴 TC-134. Нет Q-идентификатора - второго источника нет: год роняем, P577 не трогаем.

    Латинописанное аниме русская Википедия отдаёт без ``wikibase_item`` (оригинал берётся
    из английской статьи), и спросить P577 нечем. Хоп стоит времени до меню, поэтому его и
    не делаем: год реально нужен, да спросить второй источник нечем - год остаётся
    неподтверждённым, ровно как раньше. «Атака титанов» так и держится зелёной.
    """
    from torrcast.facts import Origin, origin_either

    monkeypatch.setattr(facts_mod, "_cached_origin", lambda title, series: None)
    monkeypatch.setattr(facts_mod, "_remember_origin", lambda *a: None)
    calls: list[str] = []

    def _spy_published(entity: str, timeout: float = 1.0) -> int:
        calls.append(entity)
        return 2015

    monkeypatch.setattr(facts_mod, "published_year", _spy_published)
    lone_no_id = Origin("Attack on Titan", 2015, "Атака титанов")  # entity == ""
    monkeypatch.setattr(
        facts_mod,
        "origin_now",
        lambda title, series, timeout: Origin() if series else lone_no_id,
    )
    lone = origin_either("Атака титанов")
    assert lone.title == "Attack on Titan", "имя остаётся - справка не замолкает"
    assert lone.year is None, "без второго источника год неподтверждён"
    assert not calls, "без Q-идентификатора P577 не спрашиваем - лишний хоп ни к чему"


WHISPERS = (
    "«Шёпоты и крики» (швед. Viskningar och rop) — шведский художественный фильм в жанре "
    "психологической драмы режиссёра Ингмара Бергмана, вышедший в 1972 году."
)
BICYCLE_THIEVES = (
    "«Похитители велосипедов» (итал. Ladri di biciclette) — драма Витторио Де Сика 1948 "
    "года по одноимённому произведению Луиджи Бартолини, ставшая классикой итальянского "
    "неореализма и мирового кинематографа в целом. Стабильно входит в список лучших "
    "фильмов по версии IMDb."
)
SEVEN_SAMURAI = (
    "О сериале см. статью 7 самураев.\n\n«Семь самура́ев» (яп. 七人の侍 ситинин-но самурай) — "
    "эпическая самурайская кинодрама, поставленная режиссёром Акирой Куросавой в жанре "
    "дзидайгэки в 1954 году."
)
SAMURAI_7 = (
    "7 самураев (яп. サムライ7 Samurai 7) — аниме-ремейк фильма Акиры Куросавы «Семь "
    "самураев», снятый к 50-летию оригинала."
)


def test_the_same_words_in_another_order_are_still_the_same_picture() -> None:
    """Классику зовут по памяти: «Крики и шёпот» - это статья «Шёпоты и крики».

    Слово в слово такие имена не сходятся ничем, и справка молчала - а поиск уходил в
    индексер транслитом ``kriki i shepot`` (ноль строк на живом стенде) вместо
    ``Viskningar och rop`` (девять).
    """
    page = _page("Шёпоты и крики", WHISPERS, english="Cries and Whispers")

    assert facts_mod.read_origin([page], "Крики и шёпот").title == "Viskningar och rop"
    assert facts_mod.akin("Крики и шёпот", "Шёпоты и крики")
    assert facts_mod.akin("Семнадцать мгновений весны", "Семнадцать мгновений весны")


def test_a_reshuffled_name_is_not_a_licence_to_take_a_neighbour() -> None:
    """Послабление тесное: слов поровну, каждому пара, и одно слово так не сверяется вовсе.

    Иначе «Восхождение» совпало бы с «Ганнибал: Восхождение», а «Персона» - с «Персонажем»:
    ровно те подмены, ради которых :func:`~torrcast.facts.akin` и написана.
    """
    assert not facts_mod.akin("Восхождение", "Ганнибал: Восхождение")
    assert not facts_mod.akin("Персона", "Персонаж")
    assert not facts_mod.akin("Крики и шёпот", "Крики и шорох")
    assert not facts_mod.akin("Тачки 2", "Тачки 3")


def test_the_pointer_line_at_the_top_is_not_the_pictures_own_sentence() -> None:
    """«О сериале см. статью 7 самураев.» - это разводка одноимённого, а не фраза о картине.

    Читая её первой фразой, справка видела у фильма Куросавы слово «сериале», отвергала
    его статью как чужой тип и уходила в соседнюю - аниме-ремейк, - откуда приносила
    ``Samurai 7`` оригиналом классики 1954 года. Тихая подмена картины: поиск ушёл бы в
    индексер именем совсем другого кино.
    """
    assert facts_mod.sentence(SEVEN_SAMURAI).startswith("«Семь самура́ев»")

    pages = [_page("Семь самураев", SEVEN_SAMURAI, english="Seven Samurai")]
    assert facts_mod.read_origin(pages, "Семь самураев", trusted=True, series=False).title == (
        "Seven Samurai"
    )
    # А сам ремейк остаётся собой: указатель отрезан только там, где он есть.
    remake = _page("7 самураев", SAMURAI_7, english="Samurai 7")
    assert facts_mod.read_origin([remake], "7 самураев", trusted=True).title == "Samurai 7"


def test_a_classic_that_never_says_the_word_film_still_gives_its_original() -> None:
    """Паспортная формула произведения: название в кавычках, жанр и год выхода.

    Статья о «Похитителях велосипедов» слова «фильм» в именительном не говорит ни разу
    («драма Витторио Де Сика 1948 года»), и прежний гейт молчал на классике, которую знает
    любой каталог: ``Ladri di biciclette`` - шесть строк на живом стенде против нуля у
    транслита ``pokhititeli velosipedov``.
    """
    page = _page("Похитители велосипедов", BICYCLE_THIEVES, english="Bicycle Thieves")

    found = facts_mod.read_origin([page], "Похитители велосипедов", trusted=True, series=False)
    assert found.title == "Ladri di biciclette"
    assert found.year == 1948


def test_the_passport_formula_does_not_open_the_gate_to_books_and_people() -> None:
    """Третий путь гейта не отменяет первых двух ограждений: чужое так же молчит.

    Роман Герберта открывается кавычками и годом, но жанра кино у него нет; у человека нет
    и кавычек. Стоит пустить их дальше - и справка выдаст «Dune» или «William Bradley Pitt»
    за оригинальное название картины.
    """
    for heading, extract in NOT_CINEMA.items():
        page = _page(heading, extract, english=heading)

        assert not facts_mod.read_origin([page], heading.split(" (")[0], trusted=True), heading


HP_FRANCHISE = (
    "Га́рри По́ттер (англ. Harry Potter) — серия фильмов, основанных на книгах о Гарри "
    "Поттере английской писательницы Дж. К. Роулинг."
)
HP_PHOENIX = (
    "«Га́рри По́ттер и О́рден Фе́никса» (англ. Harry Potter and the Order of the Phoenix) — "
    "фэнтезийно-приключенческий фильм 2007 года режиссёра Дэвида Йейтса, пятый из серии "
    "фильмов о Гарри Поттере."
)
HP_PRINCE = (
    "«Га́рри По́ттер и Принц-полукро́вка» (англ. Harry Potter and the Half-Blood Prince) — "
    "фэнтезийно-приключенческий фильм 2009 года режиссёра Дэвида Йейтса, шестой из серии "
    "фильмов о Гарри Поттере."
)
HP_AZKABAN = (
    "«Га́рри По́ттер и у́зник Азкаба́на» (англ. Harry Potter and the Prisoner of Azkaban) — "
    "фэнтезийно-приключенческий фильм 2004 года, третий из серии фильмов о Гарри Поттере."
)
STEINS_GATE = (
    "Steins;Gate (яп. シュタインズ ゲート Сютайндзу Гэ:то, «Врата;Штейна», МФА: [staɪnz ɡeɪt]) — "
    "японская визуальная новелла, разработанная компаниями 5pb. и Nitroplus. Является "
    "второй игрой в серии Science Adventure. 20 августа 2026 года выйдет ремейк новеллы."
)
SALTBURN = (
    "«Солтберн» (англ. Saltburn) — американский художественный фильм 2023 года в жанре "
    "чёрной комедии и психологической драмы, режиссёра Эмиральд Феннел."
)
SURPRISED = (
    "«Человек, который удивил всех» — драматический фильм режиссёров Наташи Меркуловой и "
    "Алексея Чупова, снятый ими по собственному сценарию в 2018 году."
)


def test_a_bare_franchise_name_is_answered_by_the_franchise_or_by_nothing() -> None:
    """Голое имя франшизы частью франшизы не отвечается.

    На «гарри поттер» справка приносила паспорт ПЯТОГО фильма: статья о самой серии не
    проходила киношный гейт («серия фильмов» - косвенный падеж), а сверка заголовка
    принимала любое продолжение имени, и побеждал тот, кого выше поставил поиск. Добор
    уходил по оригиналу пятой части и приводил 79 чужих раздач одной картины - они и
    выигрывали порог живости.
    """
    parts = [
        _page("Гарри Поттер и Орден Феникса (фильм)", HP_PHOENIX),
        _page("Гарри Поттер и Принц-полукровка (фильм)", HP_PRINCE),
        _page("Гарри Поттер и узник Азкабана (фильм)", HP_AZKABAN),
    ]
    whole = _page(
        "Гарри Поттер (серия фильмов)", HP_FRANCHISE, english="Harry Potter (film series)"
    )

    found = facts_mod.read_origin([whole, *parts], "гарри поттер")
    assert found.title == "Harry Potter", "имя франшизы - ровно то, которым её подписывают"
    assert found.name == "Гарри Поттер"
    assert found.year is None, "у серии фильмов года нет, и выдумывать его нечем"
    # Статьи о серии нет - молчание: выбрать часть за человека справка не вправе.
    assert not facts_mod.read_origin(parts, "гарри поттер")
    # Продолжение одно - это уточнение имени, а не выбор части: так находится «Кингсман».
    assert facts_mod.read_origin(parts[:1], "гарри поттер").title.startswith("Harry Potter and")


def test_a_franchise_article_passes_the_cinema_gate_but_a_biography_still_does_not() -> None:
    """Поблажка «серия фильмов» ровно одна и косвенный падеж вообще не открывает.

    Слово «фильмов» ловится только в связке со словом «серия»: у Эммы Уотсон в статье
    стоит «в фильмах о Гарри Поттере», и её паспорт справке по-прежнему не достаётся.
    """
    assert facts_mod._about_cinema("Гарри Поттер (серия фильмов)", HP_FRANCHISE)
    assert not facts_mod._about_cinema(
        "Уотсон, Эмма",
        "Эмма Шарлотта Дюэрре Уотсон (англ. Emma Charlotte Duerre Watson) — "
        "британская актриса, известная по ролям в фильмах о Гарри Поттере.",
    )


def test_a_redirect_to_a_latin_heading_gives_the_original_name_without_a_year() -> None:
    """Русское имя аниме, подписанного латиницей: перенаправление и есть ответ.

    «врата штейна» - живое перенаправление Википедии на статью ``Steins;Gate``, но статья
    эта о визуальной новелле, с которой всё началось, и киношного гейта она не проходит.
    Справка молчала, добор шёл транслитом ``vrata shteyna`` в никуда.

    Год такой статьи брать нельзя вовсе: у ``Steins;Gate`` во врезке стоит «20 августа 2026
    года выйдет ремейк новеллы», а аниме вышло в 2011-м. Год сильнее выдачи, и чужим годом
    гейт добора выкинул бы всю картину.
    """
    names = ["врата штейна"]
    hops = {"врата штейна": "Врата штейна", "Врата штейна": "Steins;Gate"}
    pages = {"Steins;Gate": _page("Steins;Gate", STEINS_GATE, english="Steins;Gate")}

    found = facts_mod.redirected_name(names, hops, pages, "врата штейна")
    assert found.title == "Steins;Gate"
    assert found.year is None
    # Без перенаправления пути нет: заголовок мы назвали сами, и доказывать им нечего.
    assert not facts_mod.redirected_name(["Steins;Gate"], {}, pages, "Steins;Gate"), (
        "спросили латиницей - это не перенаправление русского имени"
    )


def test_a_redirect_to_a_person_is_not_an_original_name() -> None:
    """Граница узкого пути: заголовок обязан быть латиницей, а статья - произведением."""
    pages = {
        "Дитрих Марлен": _page(
            "Дитрих Марлен",
            "Мари Магдалена Дитрих (нем. Marie Magdalene Dietrich) — немецкая актриса.",
        ),
        "Nokia": _page("Nokia", "Nokia Corporation — финская транснациональная компания."),
    }
    assert not facts_mod.redirected_name(
        ["марлен дитрих"], {"марлен дитрих": "Дитрих Марлен"}, pages, "марлен дитрих"
    )
    assert not facts_mod.redirected_name(["нокиа"], {"нокиа": "Nokia"}, pages, "нокиа")


def test_a_name_spelled_another_way_is_recognised_only_when_it_is_almost_the_same() -> None:
    """Сверка последнего шага: одна буква или одно слово, и ни шагу дальше.

    «Сальтберн» и «Солтберн» - одно имя в двух транскрипциях (транслитом расхождение ровно
    в букву), «мужчина который удивил всех» и «Человек, который удивил всех» - одно имя, в
    котором человек помнит не то одно слово из четырёх. А «Сальтерас» и «Сальтенья»,
    которые подсказчик Википедии приносит тем же списком, - уже другие имена.
    """
    assert facts_mod._near_name("сальтберн", "Солтберн")
    assert facts_mod._near_name("мужчина который удивил всех", "Человек, который удивил всех")
    assert not facts_mod._near_name("сальтберн", "Сальтерас")
    assert not facts_mod._near_name("сальтберн", "Сальтенья")
    assert not facts_mod._near_name("сальтберн", "Салитерник, Цви")
    # Коротким именам одна буква не прощается: это уже другая картина.
    assert not facts_mod._near_name("Психо", "Психи")
    # Двух слов из четырёх мало: половину имени человек не выдумывает.
    assert not facts_mod._near_name("мужчина который удивил свету", "Человек, который удивил всех")


def test_one_word_apart_counts_by_letters_not_by_words() -> None:
    """🔴 TC-284. Одно слово из трёх - ещё не описка: смотрим, что за ним осталось.

    Прежняя мерка считала слова, и «одно из трёх» принимала любое: описку («мужчина» вместо
    «человек») и чужую картину («Все мы незнакомцы» против «Все мы убийцы» - 2023 и 1952
    годов) одинаково. Разница между ними не в числе слов, а в том, сколько имени стоит за
    совпадением: «который удивил всех» - это семнадцать букв против семи, а «Все мы» -
    пять против десяти, и найдено оно ровно тем, чем подсказчик Википедии искал.

    На наборе из 36 пар имён (описки, другие переводы, соседние части франшиз,
    однофамильцы) прежняя мерка принимала все 18 чужих картин, эта - пять, и ни одной
    верной пары при этом не потеряла.
    """
    # Совпавшее перевешивает - имя то же, пусть человек и помнит не то слово.
    assert facts_mod._near_name("полет над гнездом кукушки", "Пролетая над гнездом кукушки")
    assert facts_mod._near_name("старикам здесь не место", "Старикам тут не место")
    assert facts_mod._near_name("властелин колец две крепости", "Властелин колец: Две башни")
    # Совпало одно лёгкое начало, а спорит всё остальное - это другая картина.
    assert not facts_mod._near_name("Все мы незнакомцы", "Все мы убийцы")
    assert not facts_mod._near_name("побег из претории", "Побег из Шоушенка")
    assert not facts_mod._near_name("дом у озера", "Дом у дороги")
    assert not facts_mod._near_name("ночь в музее", "Ночь в Роксбери")
    assert not facts_mod._near_name("однажды в америке", "Однажды в Голливуде")
    assert not facts_mod._near_name("сумерки сага затмение", "Сумерки. Сага. Новолуние")
    # Эталоны TC-253 остаются при своём: то же имя мерка по-прежнему знает.
    assert facts_mod._near_name("сальтберн", "Солтберн")
    assert facts_mod._near_name("мальчик и цапля", "Мальчик и птица")


def test_an_almost_the_same_name_still_gives_up_its_picture() -> None:
    """Прошедшая сверку статья читается как выборка по имени - но всегда без года.

    Имя тут не доказано, а признано похожим, и цена ошибки у полей разная: именем добор
    ищет раздачи, а год объявлен сильнее выдачи.
    """
    saltburn = _page("Солтберн", SALTBURN, english="Saltburn (film)")
    surprised = _page(
        "Человек, который удивил всех", SURPRISED, english="The Man Who Surprised Everyone"
    )

    assert facts_mod.read_origin([saltburn], "сальтберн", trusted=True).title == "Saltburn"
    found = facts_mod.read_origin([surprised], "мужчина который удивил всех", trusted=True)
    assert found.title == "The Man Who Surprised Everyone"
    assert found.name == "Человек, который удивил всех"


STRANGERS = (
    "«Все мы убийцы» (фр. Nous sommes tous des assassins) — французский художественный "
    "фильм режиссёра Андре Кайата, вышедший на экраны в 1952 году."
)


def test_the_same_name_and_the_almost_the_same_name_are_not_one_yardstick() -> None:
    """🔴 TC-253. Одна буква - то же имя, одно слово из трёх - уже другая картина.

    Мерки две, и они разные. «Сальтберн» и «Солтберн» - одно имя в двух транскрипциях,
    и добору по нему верить можно. А «Все мы незнакомцы» и «Все мы убийцы» расходятся
    ровно одним словом из трёх - и это картины 2023 и 1952 годов. Прежняя, единственная
    мерка (:func:`~torrcast.facts._near_name`) не различала их вовсе.
    """
    assert facts_mod.same_name("сальтберн", "Солтберн")
    assert facts_mod.same_name("Уэнсдей", "Уэнздей")
    assert facts_mod.same_name("Крики и шёпот", "Шёпоты и крики")
    assert not facts_mod.same_name("Все мы незнакомцы", "Все мы убийцы")
    assert not facts_mod.same_name("мужчина который удивил всех", "Человек, который удивил всех")
    # Послабление на слово живёт там, где и жило: в сверке последнего шага справки.
    assert facts_mod._near_name("мужчина который удивил всех", "Человек, который удивил всех")


def test_a_part_number_is_neither_a_typo_nor_the_whole_franchise() -> None:
    """🔴 TC-338. Номер части в имени - не описка, а часть франшизы - не целое.

    Цифра - одна буква, и разбор «одна правка по слагу» прощал её как неверно нажатую
    клавишу: «Крепкий орешек 3» проходил за «Крепкий орешек 2». А заголовок, продолжающий
    запрос частью франшизы, проходил за то же имя целиком: на голое «матрица» отвечала
    статья «Матрица: Перезагрузка». Обе пары для гейта - чужие картины под знакомым
    именем, и цена особенно высока там, где цифру заранее не режут (``titled=True``,
    «бен 10»): прикрытия больше нет, а мерка строгая.
    """
    # Номер части - не описка: разница в одну цифру имени не прощается.
    assert not facts_mod.same_name("Крепкий орешек 2", "Крепкий орешек 3")
    assert not facts_mod.same_name("Крепкий орешек 3", "Крепкий орешек 2")
    assert not facts_mod.same_name("Один дома 2", "Один дома 3")
    assert not facts_mod.same_name("Час пик 2", "Час пик 3")
    # Часть франшизы - не целое: заголовок длиннее спрошенного имени.
    assert not facts_mod.same_name("матрица", "Матрица: Перезагрузка")
    assert not facts_mod.same_name("тачки", "Тачки 4")
    # Само имя при этом не пострадало: точное, с цифрой-частью названия, с подзаголовком
    # в ЗАПРОСЕ и одна буква описки - всё по-прежнему то же имя.
    assert facts_mod.same_name("бен 10", "Бен 10")
    assert facts_mod.same_name("Властелин колец: Братство кольца", "Властелин колец")
    assert facts_mod.same_name("сальтберн", "Солтберн")


def test_a_localized_name_finds_the_shorter_article_without_taking_its_namesake() -> None:
    """🔴 TC-283. Два слова прокатного имени не должны заслонять нужную статью."""
    older = _page(
        "Незнакомцы (фильм, 2008)",
        "«Незнакомцы» - американский фильм ужасов.",
        english="The Strangers",
    )
    wanted = _page(
        "Незнакомцы (фильм, 2023)",
        "«Незнакомцы» - художественный фильм режиссёра Эндрю Хэйга.",
        english="All of Us Strangers",
    )

    found = facts_mod.read_origin([older, wanted], "Все мы незнакомцы", series=False)

    assert found.title == "All of Us Strangers"
    assert found.name == "Незнакомцы"
    assert found.guessed, "сокращённый заголовок остаётся догадкой, а не точным именем"
    assert facts_mod.same_name("Все мы незнакомцы", found.name)


def test_a_name_found_by_likeness_says_so_in_the_passport(monkeypatch: Any) -> None:
    """🔴 TC-253. Имя, найденное по сходству, помечается: гейту добора это не имя картины.

    Спросили «мужчина который удивил всех» - статьи с таким заголовком в Википедии нет, и
    поиск по куску приводит к «Человек, который удивил всех»: слово человек помнит не то,
    а имя за ним стоит целиком. Паспорт отдаётся (имя латиницей всё-таки лучше транслита),
    но отдаётся с отметкой ``guessed``: тождества имён тут никто не доказывал, и решать,
    можно ли на нём строить второй заход, будет гейт добора.
    """
    close = _page("Человек, который удивил всех", SURPRISED, english="The Man Who Surprised")
    monkeypatch.setattr(facts_mod, "_suggested", lambda query, timeout: [])
    monkeypatch.setattr(facts_mod, "_by_phrase", lambda title, timeout: [close])

    found = facts_mod._misremembered("мужчина который удивил всех", False, 1.0)

    assert found.title == "The Man Who Surprised"
    assert found.name == "Человек, который удивил всех"
    assert found.guessed, "имя лишь похоже - паспорт обязан это сказать"
    assert found.year is None


def test_a_stranger_one_word_away_is_not_offered_at_all(monkeypatch: Any) -> None:
    """🔴 TC-284. Чужая картина в одном слове от запроса не доезжает даже догадкой.

    Статьи «Все мы незнакомцы» в Википедии нет, и подсказчик приносит «Все мы убийцы» -
    французскую картину 1952 года. Раньше её отдавали паспортом с отметкой ``guessed``, и
    дальше её ловил гейт добора (TC-253). Ловить теперь нечего: за совпавшим «Все мы»
    картины не стоит, и последний шаг справки честно остаётся ни с чем.
    """
    wrong = _page("Все мы убийцы", STRANGERS)
    monkeypatch.setattr(facts_mod, "_suggested", lambda query, timeout: [wrong])
    monkeypatch.setattr(facts_mod, "_by_phrase", lambda title, timeout: [])

    found = facts_mod._misremembered("Все мы незнакомцы", False, 1.0)

    assert not found.title, "чужой оригинал уводит добор к чужой картине"
    assert not found.name
    assert not found.guessed


def test_the_likeness_mark_survives_the_cache_and_the_both_types_mode(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """Отметка «имя лишь похоже» доезжает и до диска, и через режим «оба типа».

    Без диска гейт добора на втором показе той же картины поверил бы догадке как
    доказанному имени, а без режима «оба типа» - на первом же: пустая русская выдача тем
    и отличается, что тип картины спросить неоткуда (:func:`~torrcast.facts.origin_either`).
    """
    from torrcast.facts import Origin

    monkeypatch.setattr(facts_mod, "CACHE_PATH", tmp_path / "facts.json")
    guess = Origin(title="Nous sommes tous des assassins", name="Все мы убийцы", guessed=True)
    monkeypatch.setattr(
        facts_mod, "origin_now", lambda title, series, timeout: Origin() if series else guess
    )

    lone = facts_mod.origin_either("Все мы незнакомцы", 1.0)
    assert lone.guessed, "режим «оба типа» отметку не теряет"

    assert facts_mod._cached_origin("Все мы незнакомцы", False) == guess


def test_both_types_together_fit_into_one_budget_not_two(monkeypatch: Any) -> None:
    """🔴 TC-243. Бюджет режима «оба типа» - СРОК на весь поход, а не мерка на каждый шаг.

    Одинокий ответ (:func:`~torrcast.facts.origin_either`) отправлялся за подтверждением
    года ко второму источнику со своим полным бюджетом СВЕРХ уже потраченного, и режим
    стоил вдвое дороже обещанного. Пока потолок был полторы секунды, лишняя терялась в
    шуме; на пустой выдаче справке отдают весь остаток цели (TC-243) - и эти «вдвое»
    становятся всей целью до картинки.

    Здесь оба пути отвечают на исходе срока, а Wikidata молчит дольше, чем его осталось.
    Правильный ответ - вернуться в срок БЕЗ года: неподтверждённый год честнее чужого, а
    ждать его дольше обещанного нельзя. До правки тот же поход занимал почти два бюджета.
    """
    from torrcast.facts import Origin, origin_either

    budget = 1.0
    monkeypatch.setattr(facts_mod, "_cached_origin", lambda title, series: None)
    monkeypatch.setattr(facts_mod, "_remember_origin", lambda *a: None)
    lone = Origin("Moana", 2016, "Моана", "Q1")

    def slow_paper(title: str, series: bool, timeout: float) -> Origin:
        time.sleep(budget * 0.8)  # оба пути уложились в срок, но съели почти весь
        return Origin() if series else lone

    def slow_wikidata(entity: str, timeout: float = 1.0) -> int:
        time.sleep(budget)  # остатка срока на второй источник уже нет
        return 2016

    monkeypatch.setattr(facts_mod, "origin_now", slow_paper)
    monkeypatch.setattr(facts_mod, "published_year", slow_wikidata)
    started = time.monotonic()
    found = origin_either("Моана", budget=budget)
    elapsed = time.monotonic() - started

    assert found.title == "Moana", "имя одинокого ответа остаётся - справка не замолкает"
    assert found.year is None, "второй источник не успел - год неподтверждён, и мы молчим"
    assert elapsed < budget * 1.4, f"обещали {budget} с, ушло {elapsed:.2f} с"


# --- Офлайн-карта русских прокатных имён IMDb (:data:`RU_NAMES_PATH`) ----------------
#
# Картина без русской статьи в Википедии (типичное документальное) справке недоступна по
# построению: ни выборка по имени, ни поиск статью не находят. Русское прокатное имя при
# этом живёт в выгрузке IMDb парой к оригиналу и году - карта и отвечает без сети.
RU_MAP = (
    "Американская фабрика\ttt9351980\tmovie\tAmerican Factory\t2019\n"
    # Русская картина: оригинал на кириллице, латинского имени у неё нет по построению.
    "Колыма - родина нашего страха\ttt1132100\tmovie\tКолыма - родина нашего страха\t2019\n"
    # Одно русское имя у фильма и у сериала - их разводит подсказанный тип.
    "Пятая власть\ttt1111111\tmovie\tThe Fifth Estate\t2013\n"
    "Пятая власть\ttt2222222\ttvSeries\tFifth Power\t2001\n"
    # Одно русское имя у двух фильмов - выбор между ними делает число голосов.
    "Совпадение\ttt3333333\tmovie\tJust Coincidence\t2001\n"
    "Совпадение\ttt4444444\tmovie\tMere Coincidence\t1989\n"
)


def _ru_map(monkeypatch: Any, tmp_path: Any, rows: str = RU_MAP, votes: str = "") -> None:
    """Карта и голоса из временных файлов; кэши разбора сброшены, чтобы читались они."""
    names = tmp_path / "imdb-ru-names.tsv"
    names.write_text(rows, encoding="utf-8")
    ratings = tmp_path / "imdb-ratings.tsv"
    ratings.write_text("tconst\taverageRating\tnumVotes\n" + votes, encoding="utf-8")
    monkeypatch.setattr(facts_mod, "RU_NAMES_PATH", names)
    monkeypatch.setattr(facts_mod, "RATINGS_PATH", ratings)
    monkeypatch.setattr(facts_mod, "_RU_NAMES", None)
    monkeypatch.setattr(facts_mod, "_VOTES", None)


def test_a_picture_without_an_article_gets_its_original_from_the_offline_map(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """Статьи нет, а прокатное имя есть: карта отдаёт оригинал и год, и это не догадка."""
    _ru_map(monkeypatch, tmp_path)
    found = facts_mod._imdb_ru("Американская фабрика", False)
    assert found.title == "American Factory"
    assert found.year == 2019
    assert found.name == "Американская фабрика"
    assert not found.guessed, "пара «имя - картина» из выгрузки - утверждение каталога"


def test_the_map_matches_despite_case_and_punctuation(monkeypatch: Any, tmp_path: Any) -> None:
    """Регистр и разделители имя не меняют: ключ карты нормализован с обеих сторон."""
    _ru_map(monkeypatch, tmp_path)
    found = facts_mod._imdb_ru("американская  ФАБРИКА!", False)
    assert found.title == "American Factory"


def test_the_map_honors_the_spelled_out_type(monkeypatch: Any, tmp_path: Any) -> None:
    """Фильм и сериал под одним русским именем разводятся подсказанным типом."""
    _ru_map(monkeypatch, tmp_path)
    movie = facts_mod._imdb_ru("Пятая власть", False)
    series = facts_mod._imdb_ru("Пятая власть", True)
    assert (movie.title, movie.year) == ("The Fifth Estate", 2013)
    assert (series.title, series.year) == ("Fifth Power", 2001)


def test_several_namesakes_are_a_guess_chosen_by_the_crowd(monkeypatch: Any, tmp_path: Any) -> None:
    """Два фильма под одним именем - выбирает число голосов, и паспорт помечен догадкой."""
    _ru_map(monkeypatch, tmp_path, votes="tt3333333\t7.0\t120\ntt4444444\t7.4\t68000\n")
    found = facts_mod._imdb_ru("Совпадение", False)
    assert found.title == "Mere Coincidence"
    assert found.guessed, "выбор по голосам - чья-то оценка, а не утверждение каталога"


def test_namesakes_without_votes_stay_silent(monkeypatch: Any, tmp_path: Any) -> None:
    """Однофамильцы есть, а голосов нет - неподтверждённый выбор хуже пустого паспорта."""
    _ru_map(monkeypatch, tmp_path)
    assert not facts_mod._imdb_ru("Совпадение", False)


def test_a_russian_original_is_a_year_not_a_latin_name(monkeypatch: Any, tmp_path: Any) -> None:
    """У русской картины нет латинского имени: карта отдаёт год, а ``title`` пуст."""
    _ru_map(monkeypatch, tmp_path)
    found = facts_mod._imdb_ru("Колыма - родина нашего страха", False)
    assert found.title == "", "кириллический оригинал - не имя для добора латиницей"
    assert found.year == 2019
    assert found.name == "Колыма - родина нашего страха"


def test_a_missing_map_file_is_silence_not_a_crash(monkeypatch: Any, tmp_path: Any) -> None:
    """Нет файла карты (установка без справки) - паспорт пуст, и это не сбой."""
    monkeypatch.setattr(facts_mod, "RU_NAMES_PATH", tmp_path / "no-such-file.tsv")
    monkeypatch.setattr(facts_mod, "_RU_NAMES", None)
    assert not facts_mod._imdb_ru("Американская фабрика", False)


def test_the_map_answers_when_wikipedia_does_not_know_the_name(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """Все шаги Википедии промолчали - паспорт приходит из офлайн-карты, без сети."""
    _ru_map(monkeypatch, tmp_path)
    monkeypatch.setattr(
        facts_mod,
        "get_json",
        lambda *a: {"query": {"pages": []}},  # сеть «не знает»
    )
    found = facts_mod.origin_now("Американская фабрика", False, 1.0)
    assert found.title == "American Factory"
    assert found.year == 2019


def test_an_article_answer_is_never_overridden_by_the_map(monkeypatch: Any, tmp_path: Any) -> None:
    """Статья нашлась - карта не спрашивается вовсе: она последний шаг, а не поправка."""
    _ru_map(monkeypatch, tmp_path, rows="Тачки\ttt0000001\tmovie\tWrong Title\t1900\n")

    def wiki(
        host: str, path: str, params: dict[str, str], headers: dict[str, str], t: float
    ) -> Any:
        if params.get("generator"):  # поиск и подсказки сюда не доходят
            raise AssertionError("статья нашлась прямой выборкой - поиск не нужен")
        return _wiki_reply()

    monkeypatch.setattr(facts_mod, "get_json", wiki)
    found = facts_mod.origin_now("Тачки", False, 1.0)
    assert found.title == "Cars"
    assert found.year == 2006


def test_own_name_first_prefers_the_article_named_like_the_query() -> None:
    """Прямая выборка: тёзка запроса сильнее одноимённой подмены по алфавиту уточнений.

    Живой случай: спросили «девять», а уточнение «(мультфильм)» стоит в перечне раньше
    «(фильм)», и первая же киношная статья побеждала - справка отвечала про «9»
    (мультфильм), когда статья «Девять (фильм)» названа ровно спрошенным словом.
    """
    pages: list[Any] = [
        {"title": "9 (число)"},
        {"title": "9 (мультфильм, 2009)"},
        {"title": "Девять (фильм)"},
        None,
    ]

    out = facts_mod._own_name_first(pages, "девять")

    assert out[0] == {"title": "Девять (фильм)"}, "тёзка идёт первой"
    assert out[1:] == [*pages[:2], None], "порядок остальных не тронут"


def test_own_name_first_keeps_redirected_spellings_in_the_race() -> None:
    """Перенаправленное написание («Уэнсдей» → «Уэнздей») не выбывает - оно просто следом."""
    pages: list[Any] = [{"title": "Уэнздей (телесериал)"}]

    assert facts_mod._own_name_first(pages, "уэнсдей") == pages
