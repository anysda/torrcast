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
    Fact,
    Facts,
    confirms,
    hms,
    ratings,
    read_sparql,
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


def test_the_description_is_one_sentence_cut_to_the_terminal() -> None:
    """Длинную статью режем по границе фразы, а совсем узкий терминал — по слову."""
    assert shorten(CARS, 200).endswith("Walt Disney Pictures.")
    assert "Режиссёром" not in shorten(CARS, 200), "вторая фраза в меню не нужна"
    narrow = shorten(CARS, 40)
    assert len(narrow) <= 41 and narrow.endswith("…")


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
    assert printed[3] == "  3. Моана 2 (2024)", "у остальных справки нет — и лишних строк нет"


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
