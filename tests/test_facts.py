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
    # Раздачи подписывают старое кино развёрнуто — короткое имя тоже надо попробовать.
    assert "Моана" in titles_for("Моана: романтика золотого века", 1926)


def test_the_year_in_the_text_is_what_confirms_the_picture() -> None:
    """Единственная защита от чужого фильма — год в первых фразах статьи."""
    assert confirms(MOANA, 2016)
    assert not confirms(MOANA, 2026), "мультфильм 2016 года не выдать за ремейк"
    assert not confirms(MOANA_2026, 2026), "года в тексте нет — значит, подтвердить нечем"
    assert not confirms(CARS, None), "год картины неизвестен — сверять не с чем"


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
    assert "…" not in shorten(CARS), "фраза влезла в потолок — резать нечего"


def test_only_a_sentence_past_the_cap_gets_an_ellipsis() -> None:
    """Многоточие остаётся ровно для фраз длиннее всякого разумного потолка."""
    long_one = "«Оппенгеймер» (англ. Oppenheimer) — " + "очень длинное описание, " * 20
    cut = shorten(long_one)
    assert len(cut) <= BLURB_CAP + 1 and cut.endswith("…")
    assert not cut.endswith(",…"), "хвост запятой перед многоточием не нужен"
    assert shorten("«Тачки» — мультфильм. Вторая фраза.", 10) == "«Тачки»…"


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
    assert printed[-1] == "  3. Моана 2 (2024)", "у остальных справки нет — и лишних строк нет"


def test_the_description_wraps_by_words_under_the_terminal() -> None:
    """Описание переносится по словам, каждая строка — с тем же отступом и в ширину."""
    from tests.test_cli import _moana_franchise

    facts = Facts([])
    facts.start()
    facts.found = {("Моана", 2016): Fact(about=MOANA)}
    printed = cli.menu_lines(_moana_franchise(), facts, width=60).splitlines()
    blurb = [line for line in printed if line.startswith("     ")]
    assert len(blurb) > 1, "фраза не влезла в одну строку — значит, перенеслась"
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
CLIMBERS = (
    "«Восхождение» (англ. The Climbers) — китайский фильм 2019 года режиссёра Дэниела Ли."
)


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
