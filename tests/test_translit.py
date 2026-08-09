"""Русское название, а раздачи подписаны латиницей: второй заход поиска.

Половина каталога подписана только на латинице («Psycho.1960.1080p»), и русский
запрос до неё не достаёт: индексер ищет по имени раздачи. Здесь проверяется, что
torrcast сам догадывается переспросить, откуда он берёт оригинальное название и
что на полной выдаче второго запроса не случается вовсе.

Отдельный набор - гейт добора: чужая картина под тем же русским именем не должна
проехать молча, даже если раздач от неё стало заметно больше.
"""

from __future__ import annotations

import io
from typing import Any

import pytest

from torrcast import NotFoundError, cli
from torrcast.console import Progress
from torrcast.facts import Origin
from torrcast.parse import (
    THIN_POOL,
    Picture,
    Release,
    alt_query,
    parse_release_name,
    slugify,
    transliterate,
    unswap_layout,
)
from torrcast.search import RawResult, merge
from torrcast.state import Config

GB = 1024**3


def _knows(monkeypatch: pytest.MonkeyPatch, passports: dict[str, Origin]) -> list[str]:
    """Подложить справке готовые паспорта и записывать, о чём её спрашивали."""
    asked: list[str] = []

    def about(title: str, series: bool = False, budget: float = 0.0) -> Origin:
        asked.append(title)
        return passports.get(title, Origin())

    monkeypatch.setattr(cli, "origin", about)
    return asked


def raw(
    name: str,
    number: int,
    seeders: int = 100,
    indexer: str = "Knaben",
    size: float = 8 * GB,
) -> RawResult:
    """Строка выдачи: hash различает раздачи, по нему же они и склеиваются."""
    return RawResult(
        title=name, info_hash=f"{number:040x}", size=int(size), seeders=seeders, indexer=indexer
    )


def ru(name: str) -> Release:
    return parse_release_name(name)


def test_transliterate_writes_russian_title_in_latin() -> None:
    assert transliterate("Брат") == "brat"
    assert transliterate("Ёлки") == "elki"
    assert transliterate("Щука") == "shchuka"
    assert transliterate("Иван Васильевич") == "ivan vasilevich"


def test_transliterate_keeps_latin_and_digits() -> None:
    assert transliterate("Матрица 2") == "matritsa 2"
    assert transliterate("The Matrix") == "the matrix"


def test_alt_query_takes_original_title_from_the_thin_results() -> None:
    """Оригинал из выдачи точнее транслита: «Психо» → Psycho, а не psikho."""
    thin = [ru("Психо / Psycho (1960) BDRip 1080p"), ru("Психо / Psycho (1960) DVDRip")]
    assert alt_query("психо", thin) == "Psycho"


def test_alt_query_prefers_the_most_common_original() -> None:
    pool = [
        ru("Сияние / The Shining (1980) BDRip 1080p"),
        ru("Сияние / The Shining (1980) DVDRip"),
        ru("Сияние / Shine (1996) DVDRip"),
    ]
    assert alt_query("сияние", pool) == "The Shining"


def test_alt_query_ignores_originals_of_other_pictures() -> None:
    """В выдаче по «психо» лежит и «Идентификация», её оригинал брать нельзя."""
    pool = [
        ru("Идентификация / Identity (2003) BDRip"),
        ru("Психо / Psycho (1960) DVDRip"),
    ]
    assert alt_query("психо", pool) == "Psycho"


def test_alt_query_falls_back_to_translit_when_nothing_was_found() -> None:
    """Выдачи нет вовсе - читать оригинал неоткуда, остаётся транслит."""
    assert alt_query("брат", []) == "brat"


def test_alt_query_does_not_transliterate_a_phrase_without_an_original() -> None:
    """Длинное имя другими буквами - заведомо пустой круг, а не другое имя картины."""
    hopeless = (
        "Американская фабрика",
        "13-я поправка",
        "Супер размер меня",
        "Колыма - родина нашего страха",
        "Двадцать шагов до славы",
        "Оазис: Суперзвуковой",
    )

    assert [alt_query(title, []) for title in hopeless] == [""] * len(hopeless)


def test_alt_query_is_empty_for_a_latin_request() -> None:
    """Спросили латиницей - добирать нечем, второго захода не бывает."""
    assert alt_query("psycho", [ru("Психо / Psycho (1960) DVDRip")]) == ""


def test_merge_keeps_each_torrent_once_and_holds_the_order() -> None:
    first, second = [raw("Психо", 1), raw("Психо", 2)], [raw("Psycho", 2), raw("Psycho", 3)]
    merged = merge(first, second)
    assert [r.title for r in merged] == ["Психо", "Психо", "Psycho"]


def test_merge_remembers_how_many_indexers_carried_the_torrent() -> None:
    """Склеили три зеркальные выдачи - раздача одна, но строк за ней три."""
    mirrors = [
        [raw("Психо / Psycho (1960) DVDRip", 1, indexer=name)]
        for name in ("Knaben", "RuTor", "Nyaa.si")
    ]
    merged = merge(*mirrors)
    assert [r.copies for r in merged] == [3]


def test_merge_does_not_count_the_same_indexer_twice() -> None:
    """Второй круг по другому имени приносит те же строки от тех же индексеров - каталог
    от этого не удваивается: считаем разные индексеры, а не сложенные круги.
    """
    ru_round = merge([raw("Психо / Psycho (1960) DVDRip", 1, indexer="Knaben")], [])
    latin_round = [raw("Psycho 1960 DVDRip", 1, indexer="Knaben")]
    assert [r.copies for r in merge(ru_round, latin_round)] == [1]


class _FakeProwlarr:
    """Индексер, который русский запрос знает хуже латинского - как живой."""

    def __init__(self, catalog: dict[str, list[RawResult]]) -> None:
        self.catalog = catalog
        self.asked: list[str] = []

    def __call__(self, url: str, apikey: str) -> _FakeProwlarr:
        return self

    def search(self, query: str, limit: int = 100) -> list[RawResult]:
        self.asked.append(query)
        found = self.catalog.get(query.casefold(), [])
        if not found:
            raise NotFoundError(f"по запросу «{query}» ничего не нашлось")
        return found

    def late(self) -> list[RawResult]:
        """Опоздавших нет: круг тут отвечает разом (TC-118)."""
        return []

    def spare(self) -> float:
        """Остаток цели: тут поиск мгновенный, поэтому цела вся (TC-228)."""
        from torrcast.search import GOAL

        return GOAL


def _catalog(russian: int, latin: int, quality: str = "DVDRip") -> _FakeProwlarr:
    """«Психо»: по-русски пара DVDRip'ов, на латинице - весь каталог в 1080p.

    ``quality`` - чем подписаны РУССКИЕ строки. Умолчание и есть беда: DVDRip мимо
    отбора, и такой пул негоден, сколько бы строк в нём ни было (TC-245). Полным и
    годным его делает ровно то, ради чего всё затевалось, - живой 1080p.
    """
    return _FakeProwlarr(
        {
            "психо": [raw(f"Психо / Psycho (1960) {quality} {i}", i) for i in range(russian)],
            "psycho": [raw(f"Psycho.1960.1080p.BluRay.x264-GRP{i}", 100 + i) for i in range(latin)],
        }
    )


def _search(client: _FakeProwlarr, query: str, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, str]:
    """План поиска и всё, что он сказал вслух."""
    monkeypatch.setattr(cli, "Prowlarr", client)
    config = Config(tv="127.0.0.1", prowlarr_apikey="KEY")
    args = cli.Args(query=query.split())
    out = io.StringIO()
    with Progress(out=out) as progress:
        return cli._search(config, args, progress), out.getvalue()


def test_thin_russian_pool_is_topped_up_by_the_latin_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Два русских DVDRip'а - повод переспросить: рядом лежит сорок 1080p."""
    client = _catalog(russian=2, latin=40)
    plans, said = _search(client, "психо", monkeypatch)

    assert client.asked == ["психо", "Psycho"]
    assert len(plans[0].picture.releases) == 42
    assert "по-русски раздач 2 - добрал по «Psycho»: стало 42" in said


def test_full_russian_pool_is_not_searched_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Счастливый путь не платит за чужую беду: полная и годная выдача - один запрос."""
    client = _catalog(russian=THIN_POOL, latin=40, quality="BDRip 1080p")
    plans, _said = _search(client, "психо", monkeypatch)

    assert client.asked == ["психо"]
    assert len(plans[0].picture.releases) == THIN_POOL


def test_a_fat_but_sd_russian_pool_asks_the_original_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-245. Толщина пула про его годность не говорит ничего.

    Замер каталога: «Оранжевый хит сезона» приезжал 57 русскими строками без единого HD,
    отбор перебирал мертвецов и сдавался, а под ``Orange Is the New Black`` лежали 93 HD.
    Тощесть тут не срабатывала ни разу - строк-то много, - и второго захода не случалось.
    """
    client = _catalog(russian=THIN_POOL + 5, latin=40)
    plans, said = _search(client, "психо", monkeypatch)

    assert client.asked == ["психо", "Psycho"], "HD ноль - это тоже повод спросить оригинал"
    assert len(plans[0].picture.releases) == THIN_POOL + 45
    assert f"по-русски раздач {THIN_POOL + 5} - добрал по «Psycho»" in said


def test_a_fat_but_dead_russian_pool_asks_the_original_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Вторая половина того же: HD в пуле есть, а сидов под ним нет.

    Порог живости тут тот же, которым меряется картина в меню
    (:data:`~torrcast.cli.ALIVE_SEEDERS`): под ним раздача не играет, и пул из таких строк
    негоден ровно так же, как пул из одного SD.
    """
    client = _FakeProwlarr(
        {
            "психо": [
                raw(f"Психо / Psycho (1960) BDRip 1080p {i}", i, seeders=cli.ALIVE_SEEDERS - 3)
                for i in range(THIN_POOL + 5)
            ],
            "psycho": [raw(f"Psycho.1960.1080p.BluRay.x264-GRP{i}", 100 + i) for i in range(40)],
        }
    )
    plans, said = _search(client, "психо", monkeypatch)

    assert client.asked == ["психо", "Psycho"]
    assert len(plans[0].picture.releases) == THIN_POOL + 45
    assert "добрал по «Psycho»" in said


def _mirror(count: int, *indexers: str, quality: str = "BDRip 1080p") -> list[RawResult]:
    """Одни и те же ``count`` раздач «Психо», принесённые каждым из индексеров.

    Так и выглядит живой круг: Knaben несёт то же, что nyaa и остальные, и после склейки
    по ``infoHash`` от трёх выдач остаётся одна.

    Раздачи годные нарочно: здесь мерится ТОЩЕСТЬ пула, и негодность (TC-245) в эту мерку
    лезть не должна - иначе тест проходил бы по другой причине, чем написано.
    """
    return merge(
        *[
            [raw(f"Психо / Psycho (1960) {quality} {i}", i, indexer=name) for i in range(count)]
            for name in indexers
        ]
    )


def test_a_mirrored_pool_is_not_mistaken_for_a_thin_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Шесть раздач от трёх зеркалящих индексеров - восемнадцать строк выдачи, и это не
    повод для второго круга: столько же строк отдавал и общий запрос, по которому мерился
    порог. Иначе цена поиска зависела бы от того, сколько индексеров дублируют друг друга.
    """
    client = _FakeProwlarr(
        {
            "психо": _mirror(6, "Knaben", "RuTor", "Nyaa.si"),
            "psycho": [raw(f"Psycho.1960.1080p.BluRay.x264-GRP{i}", 100 + i) for i in range(40)],
        }
    )

    plans, _said = _search(client, "психо", monkeypatch)

    assert client.asked == ["психо"], "зеркала склеились - но каталог от этого не обеднел"
    assert len(plans[0].picture.releases) == 6


def test_a_truly_poor_pool_still_asks_the_latin_title(monkeypatch: pytest.MonkeyPatch) -> None:
    """Те же шесть раздач, но их несёт один индексер: шесть строк - пул честно тощий,
    и второй круг по латинскому имени обязан случиться. Механизм не заглушён.
    """
    client = _FakeProwlarr(
        {
            "психо": _mirror(6, "Knaben"),
            "psycho": [raw(f"Psycho.1960.1080p.BluRay.x264-GRP{i}", 100 + i) for i in range(40)],
        }
    )

    plans, said = _search(client, "психо", monkeypatch)

    assert client.asked == ["психо", "Psycho"]
    assert len(plans[0].picture.releases) == 46
    assert "добрал по «Psycho»" in said


def test_a_series_missing_the_wanted_season_is_topped_up_by_the_season_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Сезон-пак под оригинальным именем: «ангел» его не приносит, «Angel S01» - да.

    У западного сериала русский запрос отдаёт раздачи чужих сезонов (S03, S04), а пак
    первого сезона лежит под латинским «Angel [S01-05]», до которого «ангел» не достаёт.
    Прежде отбор упирался в «раздач с сезоном 1 нет»; теперь сезонная строка по оригиналу
    его добирает - а чужое одноимённое аниме («The Angel Next Door ... S01») в пул не
    попадает: у него другой оригинал, и фильтр добора его отсекает.
    """
    _knows(monkeypatch, {})  # справка молчит - оригинал берётся из выдачи (Angel)
    client = _FakeProwlarr(
        {
            "ангел": [
                raw("Ангел / Angel [S03] (2001) WEB-DL 1080p", 1),
                raw("Ангел / Angel [S04] (2003) WEB-DL 1080p", 2),
            ],
            "angel s01": [
                raw("Ангел / Angel [S01-05] (1999) DVDRip | ТВ3", 3, seeders=0),
                raw("The Angel Next Door Spoils Me Rotten S01 1080p", 4),
            ],
        }
    )
    plans, said = _search(client, "ангел", monkeypatch)

    assert "Angel S01" in client.asked, "сезонная строка по оригиналу спрошена"
    packs = [r for p in plans for r in p.picture.releases if r.covers(1)]
    assert packs, "сезон-пак первого сезона добрался в план"
    assert all(slugify(r.original or "") == "angel" for r in packs), "чужого аниме в пуле нет"
    assert "сезона 1 в выдаче не было - добрал по «Angel S01»" in said


def test_a_full_season_pool_skips_the_season_string_top_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Нужный сезон в выдаче есть - лишнего круга по сезонной строке не бывает."""
    _knows(monkeypatch, {})
    client = _FakeProwlarr(
        {"ангел": [raw("Ангел / Angel [S01] (1999) WEB-DL 1080p", i) for i in range(3)]}
    )
    _plans, said = _search(client, "ангел", monkeypatch)

    assert not any(a.startswith("Angel S") for a in client.asked), "сезон есть - добора нет"
    assert "добрал по" not in said


def test_nothing_found_in_russian_is_searched_by_translit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Пустая выдача - тот же случай: читать оригинал неоткуда, идём транслитом."""
    client = _FakeProwlarr({"brat": [raw(f"Brat.1997.BDRip.x264-{i}", i) for i in range(20)]})
    plans, _said = _search(client, "брат", monkeypatch)

    assert client.asked == ["брат", "brat"]
    assert len(plans[0].picture.releases) == 20


def test_second_search_that_found_nothing_leaves_the_first_result_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Добор - не обещание: не нашлось ничего нового, играем то, что было, и молчим."""
    client = _catalog(russian=3, latin=0)
    plans, said = _search(client, "психо", monkeypatch)

    assert client.asked == ["психо", "Psycho"]
    assert len(plans[0].picture.releases) == 3
    assert "добрал" not in said


def test_nothing_anywhere_is_still_an_honest_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeProwlarr({})
    with pytest.raises(NotFoundError, match="ничего не нашлось"):
        _search(client, "нетакогофильма", monkeypatch)


def test_results_full_of_strangers_are_reported_as_nothing_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Выдача есть, а картины в ней нет - это «не нашлось», а не разговор про франшизу.

    «Дети мужчин» в каталоге зовутся «Дитя человеческое», и по набранному имени приезжают
    только однофамильцы. Прежде такому человеку отвечали «такой картины во франшизе нет»,
    и он шёл проверять номер части у фильма, которого поиск вообще не видел.
    """
    client = _FakeProwlarr(
        {"дети мужчин": [raw(f"Мужчины, женщины и дети (2014) BDRip {i}", i) for i in range(20)]}
    )

    with pytest.raises(NotFoundError) as caught:
        _search(client, "дети мужчин", monkeypatch)

    assert "ничего не нашлось" in str(caught.value)
    assert "франшиз" not in str(caught.value)


def test_a_part_that_the_franchise_does_not_have_is_named_as_such(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """А вот когда франшиза нашлась, а части в ней нет - так и говорим, с числом частей."""
    client = _FakeProwlarr(
        {"матрица": [raw(f"Матрица / The Matrix (1999) BDRip {i}", i) for i in range(20)]}
    )

    with pytest.raises(NotFoundError) as caught:
        _search(client, "матрица 5", monkeypatch)

    assert "картин во франшизе 1, номера 5 нет" in str(caught.value)


def test_the_part_number_picks_inside_the_named_franchise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«гарри поттер дары смерти 2» - это часть 2011 года, и добора ей не нужно.

    Номер уходит из строки поиска (спрашиваем «гарри поттер дары смерти») и работает
    выбором картины. Пока запрос без союза «и» не совпадал с каталогом, пул выходил
    пустым, поиск шёл на второй круг по франшизе целиком и привозил антологию.
    """
    client = _FakeProwlarr(
        {
            "гарри поттер дары смерти": [
                raw(f"Гарри Поттер и Дары смерти: Часть 1 (2010) BDRip {i}", i) for i in range(20)
            ]
            + [
                raw(f"Гарри Поттер и Дары Смерти: Часть II (2011) BDRip {i}", 100 + i)
                for i in range(20)
            ]
        }
    )

    plans, _said = _search(client, "гарри поттер дары смерти 2", monkeypatch)

    assert client.asked == ["гарри поттер дары смерти"]
    assert [p.picture.year for p in plans] == [2011]


def test_a_named_part_is_not_thrown_away_by_the_year_of_the_first_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«тачки 2» - это 2011 год, и справка про «Тачки» 2006-го его не отменяет.

    Справку зовут по имени франшизы, и год она называет первой картины. Гейт добора читал
    это расхождение как подмену и выбрасывал честную выдачу: на живом каталоге «тачки 2»
    не находились вовсе.
    """
    client = _FakeProwlarr(
        {"тачки": [raw(f"Тачки 2 / Cars 2 (2011) BDRip {i}", i) for i in range(3)]}
    )
    _knows(monkeypatch, {"тачки": Origin(title="Cars", year=2006)})

    plans, said = _search(client, "тачки 2", monkeypatch)

    assert [p.picture.year for p in plans] == [2011]
    assert "в каталоге лежит картина" not in said


def test_a_year_that_disagrees_without_a_part_number_is_named_but_not_taken_away(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-248. Без номера части год справки говорит своё слово, но выдачу не отнимает.

    Спросили «тачки», справка знает первую картину 2006 года, а в каталоге под этим именем
    лежит только вторая, 2011-го. Прежде гейт выбрасывал её вместе со всей выдачей и
    отвечал «ничего не нашлось» - при живых раздачах в руках. Расхождение печатается
    строкой, картину с её годом человек видит в меню и решает сам.
    """
    client = _FakeProwlarr(
        {"тачки": [raw(f"Тачки 2 / Cars 2 (2011) BDRip {i}", i) for i in range(3)]}
    )
    _knows(monkeypatch, {"тачки": Origin(title="Cars", year=2006)})

    plans, said = _search(client, "тачки", monkeypatch)

    assert [p.picture.year for p in plans] == [2011]
    assert "под этим именем в каталоге лежит картина 2011 года, а не 2006" in said


def test_other_word_order_is_found_and_said_out_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """«бульвар сансет» играет «Сансет бульвар» - и об этом сказано вслух."""
    client = _FakeProwlarr(
        {
            "бульвар сансет": [
                raw(f"Сансет бульвар / Sunset Blvd (1950) BDRip {i}", i) for i in range(20)
            ]
        }
    )

    plans, said = _search(client, "бульвар сансет", monkeypatch)

    assert [p.picture.title for p in plans] == ["Сансет бульвар"]
    assert "«бульвар сансет» - в каталоге это «Сансет бульвар»" in said


def _namesakes() -> _FakeProwlarr:
    """«Восхождение»: фильм Шепитько 1977 года и китайский 2019-го под тем же именем.

    Оригинал ``The Climbers`` лежит прямо в русской выдаче - именно им добор и уезжал
    в чужое кино, принося два десятка раздач с дорожкой ``und``.
    """
    return _FakeProwlarr(
        {
            "восхождение": [raw(f"Восхождение (1977) DVDRip {i}", i) for i in range(4)]
            + [raw(f"Восхождение / The Climbers (2019) WEB-DL {i}", 50 + i) for i in range(2)],
            "the climbers": [
                raw(f"The.Climbers.2019.1080p.WEB-DL.x264-{i}", 100 + i) for i in range(20)
            ],
        }
    )


def _unglued() -> _FakeProwlarr:
    """Две половины одной картины, которые нечем сшить: русская и латинская.

    Дословная форма живого случая: русские раздачи «Синего экзорциста» несут оригинал,
    а латинские - только своё имя, без года и без русского названия. Кластер оставляет
    их разными картинами, и привязка к картине по русскому запросу латинскую половину
    не видит.
    """
    return _FakeProwlarr(
        {
            "синий экзорцист": [
                raw(f"Синий экзорцист / Ao no Exorcist (2011) BDRip {i}", i, seeders=1)
                for i in range(3)
            ],
            "blue exorcist": [
                raw(f"Blue Exorcist S01E{i:02d} 1080p WEB-DL", 100 + i, seeders=33)
                for i in range(1, 26)
            ],
        }
    )


def test_the_top_up_is_not_lost_on_the_binding_to_a_picture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Добор привёз картину под её латинским именем - и она обязана доехать до очереди.

    Прежде она пропадала целиком: pick_franchise по русскому запросу латинскую половину
    не находит, добор выходил «пустым», и человек оставался с тремя мёртвыми раздачами
    при двадцати пяти живых в той же выдаче.
    """
    client = _unglued()
    _knows(monkeypatch, {"синий экзорцист": Origin(title="Blue Exorcist", year=2009)})
    plans, said = _search(client, "синий экзорцист", monkeypatch)

    assert client.asked == ["синий экзорцист", "Blue Exorcist"]
    assert {p.picture.title for p in plans} == {"Синий экзорцист", "Blue Exorcist"}
    assert max(len(p.picture.releases) for p in plans) == 25
    assert "добрал по «Blue Exorcist»" in said


def test_the_reference_year_of_a_whole_franchise_does_not_kill_the_top_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Справка о сериале называет год ПЕРВОГО сезона, а картины в каталоге - свои.

    Спорить тут не о чем: у латинских раздач года нет вовсе, и разводить ими нечего.
    Раньше это расхождение (2009 у справки против 2011 в каталоге) читалось как подмена.
    """
    client = _unglued()
    _knows(monkeypatch, {"синий экзорцист": Origin(title="Blue Exorcist", year=1066)})
    _plans, said = _search(client, "синий экзорцист", monkeypatch)

    assert "приехала другая картина" not in said


def test_a_namesake_under_the_reference_name_is_still_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Ослабление точечное: имя из справки ручается за картину, но не против ГОДА.

    Справка знает «Восхождение» Шепитько как ``The Ascent`` 1977 года, а в каталоге под
    этим именем лежит чужой фильм 2019-го на двадцать раздач. Раздач больше - картина
    другая, и подмешивать её к найденному нельзя.
    """
    client = _FakeProwlarr(
        {
            "восхождение": [raw(f"Восхождение (1977) DVDRip {i}", i) for i in range(4)],
            "the ascent": [
                raw(f"The Ascent (2019) WEB-DL {i}", 100 + i, seeders=80) for i in range(20)
            ],
        }
    )
    _knows(monkeypatch, {"восхождение": Origin(title="The Ascent", year=1977)})
    plans, said = _search(client, "восхождение", monkeypatch)

    assert client.asked == ["восхождение", "The Ascent"]
    assert [p.picture.year for p in plans] == [1977]
    assert max(len(p.picture.releases) for p in plans) == 4
    assert "добрал" not in said


def test_a_subtitle_query_needs_no_second_round(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 «Кольца власти» - подзаголовок сериала, и картина находится с первого круга.

    Прежде запрос не привязывался ни к одной картине, пустой пул звал добор, тот
    приносил по оригиналу всю чужую франшизу - и гейт честно её отбраковывал вместе с
    русской выдачей. Человек читал «ничего не нашлось» при 20 живых раздачах.
    """
    client = _FakeProwlarr(
        {
            "кольца власти": [
                raw(
                    "Властелин колец: Кольца власти / The Lord of the Rings: "
                    f"The Rings of Power (2022) WEB-DL 1080p {i}",
                    i,
                    seeders=91,
                )
                for i in range(20)
            ]
        }
    )
    asked = _knows(monkeypatch, {})
    plans, said = _search(client, "кольца власти", monkeypatch)

    assert client.asked == ["кольца власти"], "лишнего круга по индексерам не нужно"
    assert asked == [], "справку тоже не тревожим: пул полон"
    assert [p.picture.title for p in plans] == ["Властелин колец: Кольца власти"]
    assert len(plans[0].picture.releases) == 20
    assert "ничего не нашлось" not in said


def test_a_dead_namesake_no_longer_swallows_a_subtitle_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-246. «Космическая одиссея»: вердикт «рой мёртв» по одной чужой раздаче.

    Под этим именем в каталоге лежит картина 1987 года с единственной мёртвой раздачей, и
    запрос доставался ей целиком - при 21 строке в пуле. Классика 1968 года подписана
    ``2001: Космическая одиссея``, её ключ - ``2001``, и до меню она не доезжала вовсе.

    Теперь в меню обе, дефолт стоит на живой, и человек читает обе стороны выбора.
    """
    client = _FakeProwlarr(
        {
            "космическая одиссея": [
                raw(
                    f"2001: Космическая одиссея / 2001: A Space Odyssey (1968) BDRip 1080p {i}",
                    i,
                    seeders=49,
                )
                for i in range(20)
            ]
            + [raw("Космическая одиссея (1987) VHSRip", 90, seeders=0)]
        }
    )
    plans, said = _search(client, "космическая одиссея", monkeypatch)

    assert [p.picture.year for p in plans] == [1987, 1968], "в меню обе картины"
    assert cli.first_alive(plans) == 2, "дефолт - живая, а не мёртвый огрызок"
    assert "«космическая одиссея» - в каталоге это «2001: Космическая одиссея»" in said
    note = cli.default_note(plans, "космическая одиссея")
    assert "«2001: Космическая одиссея (1968)»" in note and "«Космическая одиссея (1987)»" in note


def test_a_thin_subtitle_pool_is_never_zeroed_by_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Пул тощий, добор привёз чужую франшизу - гейт её не берёт, но и своё не выбрасывает."""
    client = _FakeProwlarr(
        {
            "кольца власти": [
                raw(
                    "Властелин колец: Кольца власти / The Lord of the Rings: "
                    f"The Rings of Power (2022) WEB-DL 1080p {i}",
                    i,
                    seeders=91,
                )
                for i in range(3)
            ],
            "the lord of the rings": [
                raw(f"The.Lord.of.the.Rings.The.War.of.the.Rohirrim.2024.1080p-{i}", 100 + i)
                for i in range(40)
            ],
        }
    )
    _knows(monkeypatch, {})
    plans, said = _search(client, "кольца власти", monkeypatch)

    assert client.asked == ["кольца власти", "The Lord of the Rings"]
    assert [p.picture.title for p in plans] == ["Властелин колец: Кольца власти"]
    assert len(plans[0].picture.releases) == 3, "чужая франшиза к картине не подмешана"
    assert "добрал" not in said


def test_top_up_that_brings_a_namesake_picture_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Раздач стало больше - но это раздачи другого фильма. Добор отменяется."""
    client = _namesakes()
    plans, said = _search(client, "восхождение", monkeypatch)

    assert client.asked == ["восхождение", "The Climbers"]
    assert [p.picture.year for p in plans] == [1977, 2019]
    assert max(len(p.picture.releases) for p in plans) == 4
    assert "добрал" not in said
    assert "приехала другая картина" in said


def test_the_reference_year_never_takes_away_what_the_russian_query_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-248. «Крестьяне» и «Восхождение» держатся ОДНОВРЕМЕННО, одним тестом.

    У гейта года остаётся право не ДОБАВИТЬ своё и нет права ОТНЯТЬ найденное.

    «Крестьяне»: справка знает картину 1935 года, а каталог под этим именем несёт 2023-й
    живым BDRip 1080p. Прежде гейт выбрасывал его вместе с выдачей и отвечал «ничего не
    нашлось» - честный отказ при существующем кино, то есть брак. Теперь расхождение
    сказано строкой, а картина осталась: слово справки против слова каталога решает
    человек, он видит в меню и имя, и год.

    «Восхождение»: настоящую подмену тот же гейт ловит как ловил - чужой ``The Climbers``
    2019 года к выдаче Шепитько не подмешивается, потому что там его именно ДОБАВЛЯЮТ.
    """
    peasants = _FakeProwlarr(
        {
            "крестьяне": [
                raw(f"Крестьяне / Chlopi (2023) BDRip 1080p {i}", i, seeders=44) for i in range(6)
            ]
        }
    )
    _knows(monkeypatch, {"крестьяне": Origin(year=1935)})

    plans, said = _search(peasants, "крестьяне", monkeypatch)

    assert [p.picture.title for p in plans] == ["Крестьяне"]
    assert len(plans[0].picture.releases) == 6, "живой 1080p остался в руках"
    assert "ничего не нашлось" not in said
    assert "под этим именем в каталоге лежит картина 2023 года, а не 1935" in said

    ascent, told = _search(_namesakes(), "восхождение", monkeypatch)

    assert max(len(p.picture.releases) for p in ascent) == 4, "чужая картина не подмешана"
    assert "добрал" not in told
    assert "приехала другая картина" in told


def test_the_reference_year_outweighs_the_pool_in_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Справка знает год картины - и он же отвергает однофамильца, кто бы ни был крупнее."""
    client = _namesakes()
    asked = _knows(monkeypatch, {"восхождение": Origin(year=1977)})
    plans, said = _search(client, "восхождение", monkeypatch)

    assert asked == ["восхождение"]
    assert max(len(p.picture.releases) for p in plans) == 4
    assert "добрал" not in said


def test_original_title_comes_from_the_reference_when_the_pool_has_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Оригинала в выдаче нет, транслит уходит в пустоту - выручает справка.

    ``кингсман секретная служба`` → ``kingsman sekretnaya sluzhba`` не находит ничего, и
    прежний добор на этом заканчивался. Справка знает имя картины - по нему и находится.
    """
    client = _FakeProwlarr(
        {
            "кингсман секретная служба": [
                raw(f"Кингсман Секретная служба (2014) TS {i}", i) for i in range(2)
            ],
            "kingsman": [
                raw(
                    f"Кингсман: Секретная служба / Kingsman: The Secret Service (2014) BDRip {i}",
                    100 + i,
                )
                for i in range(30)
            ],
        }
    )
    asked = _knows(monkeypatch, {"кингсман секретная служба": Origin(title="Kingsman", year=2014)})
    plans, said = _search(client, "кингсман секретная служба", monkeypatch)

    assert asked == ["кингсман секретная служба"]
    assert client.asked == ["кингсман секретная служба", "Kingsman"]
    assert max(len(p.picture.releases) for p in plans) == 32
    assert "добрал по «Kingsman»" in said


def test_a_silent_reference_leaves_the_old_path_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сети нет - справка пуста, и добор идёт прежним путём: оригинал из выдачи."""
    client = _catalog(russian=2, latin=40)
    asked = _knows(monkeypatch, {})
    plans, said = _search(client, "психо", monkeypatch)

    assert asked == ["психо"]
    assert client.asked == ["психо", "Psycho"]
    assert len(plans[0].picture.releases) == 42
    assert "добрал по «Psycho»" in said


def test_the_full_pool_asks_neither_the_indexers_nor_the_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Счастливый путь не платит ни за второй круг по индексерам, ни за справку."""
    client = _catalog(russian=THIN_POOL, latin=40, quality="BDRip 1080p")
    asked = _knows(monkeypatch, {"психо": Origin(title="Psycho", year=1960)})
    plans, _said = _search(client, "психо", monkeypatch)

    assert client.asked == ["психо"]
    assert asked == []
    assert len(plans[0].picture.releases) == THIN_POOL


def test_an_unproven_original_is_not_trusted_on_an_empty_result() -> None:
    """Сверять не с чем: до добора картины не было, справка молчит.

    Транслит - это сами слова запроса, ему веры хватает. А вот оригиналу, вычитанному у
    чужой раздачи, - нет: «не нашлось» честнее наугад взятого однофамильца.
    """
    came = Picture(title="Незнакомцы", year=2008, releases=[])

    assert cli.same_picture(None, came, Origin(), proven=True)
    assert not cli.same_picture(None, came, Origin(), proven=False)


def test_the_reference_year_decides_who_is_who() -> None:
    """Год справки сильнее всего: и подтверждает картину, и отвергает однофамильца."""
    ours = Picture(title="Восхождение", year=1977, releases=[])
    theirs = Picture(title="Восхождение", year=2019, releases=[])

    assert cli.same_picture(ours, theirs, Origin(year=2019), proven=False)
    assert not cli.same_picture(ours, theirs, Origin(year=1976), proven=True)
    # Производство и прокат расходятся на год - это не подмена.
    assert cli.same_picture(ours, ours, Origin(year=1976), proven=False)


def test_a_remake_with_the_same_original_is_not_a_substitution() -> None:
    """Ремейк с тем же оригиналом - та же картина, хоть годы и врозь.

    Справка знает «Fruits Basket» 2006, а у индексеров ремейк 2019: оригинал один и тот
    же, значит это добор той же вещи, а не подмена. А вот чужой оригинал год по-прежнему
    разводит - дыру для настоящих подмен совпадение русского имени не открывает.
    """
    remake = Picture(title="Корзинка фруктов", year=2019, original="Fruits Basket", releases=[])
    about = Origin(title="Fruits Basket", year=2006, name="Корзинка фруктов")
    assert cli.same_picture(None, remake, about, proven=True)

    # «Восхождение» Шепитько (The Ascent) против китайского (The Climbers) - разные оригиналы.
    alien = Picture(title="Восхождение", year=2019, original="The Climbers", releases=[])
    ascent = Origin(title="The Ascent", year=1976, name="Восхождение")
    assert not cli.same_picture(None, alien, ascent, proven=True)


def test_the_gate_keeps_a_series_without_a_year(monkeypatch: pytest.MonkeyPatch) -> None:
    """Годов не назвал никто (обычное дело у сериалов) - гейт сверяет франшизу и пропускает."""
    client = _FakeProwlarr(
        {
            "дедвуд": [raw(f"Дедвуд / Deadwood S01E0{i} WEB-DL", i) for i in range(1, 5)],
            "deadwood": [
                raw(f"Deadwood.S01E{i:02d}.1080p.WEB-DL.x264", 100 + i) for i in range(1, 16)
            ],
        }
    )
    plans, said = _search(client, "дедвуд", monkeypatch)

    assert client.asked == ["дедвуд", "Deadwood"]
    assert len(plans[0].picture.releases) == 19
    assert "добрал по «Deadwood»: стало 19" in said


def test_an_empty_result_asks_the_reference_by_the_query_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Русская выдача пуста - оригинал брать неоткуда, кроме справки.

    Прежде на пустой выдаче оставался только транслит («Уэнсдей» → ``uensdey``), а он
    не находит ничего: раздачи подписаны ``Wednesday``. Справку спрашиваем по САМОМУ
    запросу - она отвечает про ту картину, которую спросили, а не про ту, что попала в
    выдачу (её нет вовсе).
    """
    client = _FakeProwlarr(
        {"wednesday": [raw(f"Wednesday.S01E{i:02d}.1080p.NF.WEB-DL", i) for i in range(1, 9)]}
    )
    asked = _knows(monkeypatch, {"уэнсдей": Origin(title="Wednesday")})

    plans, said = _search(client, "уэнсдей", monkeypatch)

    assert asked == ["уэнсдей"]
    assert client.asked == ["уэнсдей", "Wednesday"]
    assert len(plans[0].picture.releases) == 8
    assert "добрал по «Wednesday»: стало 8" in said


def test_a_silent_reference_on_an_empty_result_still_goes_by_translit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Сети нет - справка пуста, и остаётся ровно то, что было: транслит запроса."""
    client = _FakeProwlarr({"brat": [raw(f"Brat.1997.BDRip.x264-{i}", i) for i in range(20)]})
    asked = _knows(monkeypatch, {})

    plans, _said = _search(client, "брат", monkeypatch)

    assert asked == ["брат"]
    assert client.asked == ["брат", "brat"]
    assert len(plans[0].picture.releases) == 20


def _refused(client: _FakeProwlarr, query: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Поиск, кончившийся отказом: всё, что при этом было сказано вслух."""
    monkeypatch.setattr(cli, "Prowlarr", client)
    config = Config(tv="127.0.0.1", prowlarr_apikey="KEY")
    out = io.StringIO()
    with Progress(out=out) as progress, pytest.raises(NotFoundError):
        cli._search(config, cli.Args(query=query.split()), progress)
    return out.getvalue()


def test_a_name_the_reference_only_guessed_does_not_bring_a_stranger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-253. Русская выдача пуста, и справка знает имя лишь по сходству - не верим.

    Живая проба: статьи «Все мы незнакомцы» в русской Википедии нет вовсе, и справка
    находит по сходству имён «Все мы убийцы» - французскую картину 1952 года. На пустой
    выдаче сверять добор не с чем (:func:`~torrcast.cli.same_picture` с ``before=None``
    решала по одному происхождению имени), и чужое кино доезжало под знакомым именем -
    худший вид брака по спеке. Теперь справка обязана назвать ту же картину тем же
    именем; назвала другим - второго захода к индексерам не делаем вовсе.
    """
    client = _FakeProwlarr(
        {
            "nous sommes tous des assassins": [
                raw(f"Nous.sommes.tous.des.assassins.1952.DVDRip.x264-{i}", i) for i in range(20)
            ]
        }
    )
    _knows(
        monkeypatch,
        {
            "все мы незнакомцы": Origin(
                title="Nous sommes tous des assassins", name="Все мы убийцы", guessed=True
            )
        },
    )

    said = _refused(client, "все мы незнакомцы", monkeypatch)

    assert client.asked == ["все мы незнакомцы"], "за чужой картиной не ходят даже разок"
    assert "справка нашла лишь похожее имя «Все мы убийцы»" in said


def test_a_shorter_article_title_brings_the_real_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-283. Прокатное имя на два слова длиннее статьи, но это та же картина."""
    client = _FakeProwlarr(
        {
            "all of us strangers": [
                raw(f"All.of.Us.Strangers.2023.1080p.WEB-DL.x264-{i}", i) for i in range(20)
            ]
        }
    )
    _knows(
        monkeypatch,
        {"все мы незнакомцы": Origin(title="All of Us Strangers", name="Незнакомцы", guessed=True)},
    )

    plans, said = _search(client, "все мы незнакомцы", monkeypatch)

    assert client.asked == ["все мы незнакомцы", "All of Us Strangers"]
    assert len(plans[0].picture.releases) == 20
    assert "оригинал «All of Us Strangers» - по справке; без неё второго запроса не было бы" in said


def test_the_same_name_in_another_spelling_is_still_topped_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """А описка в одну букву добор не отменяет: «Сальтберн» и «Солтберн» - одно имя.

    Тут справка называет ТУ ЖЕ картину, только другой транскрипцией, и это и есть второй
    признак: сверять было с чем, и сверка сошлась. Молчим и добираем, как добирали.
    """
    client = _FakeProwlarr(
        {"saltburn": [raw(f"Saltburn.2023.1080p.WEB-DL.x264-{i}", i) for i in range(20)]}
    )
    _knows(monkeypatch, {"сальтберн": Origin(title="Saltburn", name="Солтберн", guessed=True)})

    plans, said = _search(client, "сальтберн", monkeypatch)

    assert client.asked == ["сальтберн", "Saltburn"]
    assert len(plans[0].picture.releases) == 20
    assert "сверить было не с чем" not in said


def test_a_guessed_name_with_nothing_to_check_it_against_is_taken_out_loud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Сверить догадку нечем - берём, но говорим об этом: за проверенное не выдаём.

    Русская Википедия подписывает аниме латиницей, и своего русского имени у статьи нет
    вовсе. Отказывать тут не за что - имя ничему не противоречит, - но и молчать нельзя:
    человек вправе знать, что картину под его именем выбрала справка, а не выдача.
    """
    client = _FakeProwlarr(
        {"re:zero": [raw(f"Re.Zero.S01E{i:02d}.1080p.WEB-DL", i) for i in range(1, 9)]}
    )
    _knows(monkeypatch, {"ре зеро": Origin(title="Re:Zero", guessed=True)})

    plans, said = _search(client, "ре зеро", monkeypatch)

    assert client.asked == ["ре зеро", "Re:Zero"]
    assert len(plans[0].picture.releases) == 8
    assert "имя «Re:Zero» взято со справки, сверить было не с чем" in said


def test_a_name_wikipedia_itself_redirects_to_is_not_a_guess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Другое русское имя от САМОЙ Википедии - не догадка, и добор ею не отменяется.

    «Мальчик и цапля» - живое перенаправление на статью «Мальчик и птица»: это утверждение
    самой Википедии о том, что картина одна. Сверка имён тут ни при чём, отметки
    ``guessed`` у такого паспорта нет, и всё работает ровно так, как работало.
    """
    client = _FakeProwlarr(
        {
            "the boy and the heron": [
                raw(f"The.Boy.and.the.Heron.2023.1080p.BluRay-{i}", i) for i in range(20)
            ]
        }
    )
    _knows(
        monkeypatch,
        {"мальчик и цапля": Origin(title="The Boy and the Heron", name="Мальчик и птица")},
    )

    plans, said = _search(client, "мальчик и цапля", monkeypatch)

    assert client.asked == ["мальчик и цапля", "The Boy and the Heron"]
    assert len(plans[0].picture.releases) == 20
    assert "похожее имя" not in said and "сверить было не с чем" not in said


def test_the_reference_original_does_not_open_the_gate_to_another_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Оригинал из справки - proven, но год всё равно сверяется.

    Имя пришло от справки, значит оно про ту самую картину; а вот приехать по нему может
    чужое кино того же названия. Год расходится - добора не было, и это честное
    «не нашлось», а не чужой фильм.
    """
    client = _FakeProwlarr(
        {"the ascent": [raw(f"The.Climbers.2019.1080p.WEB-DL.x264-{i}", i) for i in range(20)]}
    )
    asked = _knows(monkeypatch, {"восхождение": Origin(title="The Ascent", year=1976)})

    with pytest.raises(NotFoundError):
        _search(client, "восхождение", monkeypatch)

    assert asked == ["восхождение"]
    assert client.asked == ["восхождение", "The Ascent"]


def test_the_verdict_of_a_top_up_comes_after_the_line_of_that_very_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Сначала строка круга, потом его итог - иначе это читается как противоречие.

    ``note`` печатается сразу, а строка фазы - только когда фазу закрыли, и в прежнем
    порядке «приехала другая картина» выходило ПЕРЕД «поиск «The Climbers»… 102.1 с».
    Человек читал два несвязанных сообщения как отказ, за которым будто бы последовал
    удавшийся второй поиск, из которого и выросло меню.
    """
    client = _namesakes()
    _plans, said = _search(client, "восхождение", monkeypatch)

    assert "поиск «The Climbers»" in said
    assert said.index("поиск «The Climbers»") < said.index("приехала другая картина")
    # Итог называет, на чём остались: молчаливого «не беру» человеку мало.
    assert "остаюсь на выдаче по «восхождение»" in said


def test_the_same_name_is_not_asked_a_second_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Латинский запрос уже латинский: второй круг тем же именем - чистая трата.

    На «cast cars» оригиналом из выдачи оказывается «Cars», то есть сам запрос, и добор
    уходил на полный круг по всем индексерам за той же самой выдачей: на живом стенде это
    стоило 102 секунды до меню.
    """
    client = _FakeProwlarr({"cars": [raw(f"Cars (2006) BDRip {i}", i) for i in range(3)]})
    _knows(monkeypatch, {"cars": Origin(title="Cars", year=2006)})

    plans, _said = _search(client, "cars", monkeypatch)

    assert client.asked == ["cars"]
    # Пул тощий - значит добор рассматривался и был отменён именно как бессмысленный.
    assert max(len(p.picture.releases) for p in plans) < THIN_POOL


def test_latin_query_is_topped_up_by_the_russian_title_from_the_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Спросили латиницей, а живут раздачи под русским именем - добор идёт в другую сторону.

    ``cast cars`` на живом каталоге приносил одну мёртвую англоязычную раздачу: «Тачки»
    индексер по слову ``cars`` не отдаёт вовсе. Русское имя картины знает справка - им и
    добираем, ровно как латинским именем добираем русский запрос.
    """
    client = _FakeProwlarr(
        {
            "cars": [raw("Cars (2006) 1080p WEB-DL", 1, seeders=3)],
            "тачки": [raw(f"Тачки / Cars (2006) BDRip {i}", 10 + i) for i in range(4)]
            + [raw(f"Тачки 3 / Cars 3 (2017) BDRip {i}", 20 + i) for i in range(14)],
        }
    )
    _knows(monkeypatch, {"cars": Origin(title="Cars", year=2006, name="Тачки")})

    plans, said = _search(client, "cars", monkeypatch)

    assert client.asked == ["cars", "Тачки"]
    # Картина одна на оба имени: русские раздачи в пуле, а не в соседнем пункте меню.
    cars = next(p for p in plans if p.picture.year == 2006)
    assert cars.picture.title == "Тачки"
    assert len(cars.picture.releases) == 5
    assert "добрал по «Тачки»" in said


def test_the_biggest_part_of_a_franchise_is_not_a_swapped_picture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Добор по имени от справки приносит франшизу целиком, и вожаком в ней становится
    самая раздаваемая часть. Это не подмена: картина нужного года на месте, и гейт её видит.
    """
    client = _FakeProwlarr(
        {
            "cars": [raw("Cars (2006) 1080p WEB-DL", 1, seeders=3)],
            "тачки": [raw(f"Тачки 3 / Cars 3 (2017) BDRip {i}", 20 + i) for i in range(14)]
            + [raw(f"Тачки / Cars (2006) BDRip {i}", 10 + i) for i in range(4)],
        }
    )
    _knows(monkeypatch, {"cars": Origin(title="Cars", year=2006, name="Тачки")})

    plans, said = _search(client, "cars", monkeypatch)

    assert [p.picture.year for p in plans] == [2006, 2017]
    assert "приехала другая картина" not in said


def test_a_classic_with_a_known_original_is_asked_by_it_and_not_by_translit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Неанглийская классика ищется оригиналом; транслит - запасной ход, а не первый.

    Живой замер (TC-138): «Крики и шёпот» уходили в индексер транслитом
    ``kriki i shepot`` и приносили НОЛЬ строк, тогда как под своим оригиналом
    ``Viskningar och rop`` в том же каталоге лежат девять. Транслит тут не выручает - он
    выдумывает имя, которым раздачу не подписывал никто.
    """
    client = _FakeProwlarr(
        {
            "крики и шёпот": [raw("Крики и шёпот (1972) DVDRip", 1)],
            "viskningar och rop": [
                raw(f"Viskningar och rop AKA Cries and Whispers 1972 BDRip {i}", 10 + i)
                for i in range(9)
            ],
        }
    )
    _knows(
        monkeypatch, {"крики и шёпот": Origin(title="Viskningar och rop", name="Шёпоты и крики")}
    )

    _plans, said = _search(client, "крики и шёпот", monkeypatch)

    assert client.asked == ["крики и шёпот", "Viskningar och rop"]
    assert transliterate("крики и шёпот") not in client.asked
    assert "добрал по «Viskningar och rop»: стало 10" in said


def test_the_swap_of_the_query_is_said_out_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """Смена запроса - не молчаливое дело: сказано, что имя от справки и чем искали бы без неё."""
    client = _FakeProwlarr(
        {
            "крики и шёпот": [raw("Крики и шёпот (1972) DVDRip", 1)],
            "viskningar och rop": [
                raw(f"Viskningar och rop 1972 BDRip {i}", 10 + i) for i in range(9)
            ],
        }
    )
    _knows(
        monkeypatch, {"крики и шёпот": Origin(title="Viskningar och rop", name="Шёпоты и крики")}
    )

    _plans, said = _search(client, "крики и шёпот", monkeypatch)

    assert "оригинал «Viskningar och rop» - по справке; без неё искал бы «kriki i shepot»" in said


def test_the_reference_that_says_nothing_new_keeps_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Справка назвала то же имя, что лежало в выдаче, - объявлять нечего, строки нет."""
    client = _catalog(russian=2, latin=40)
    _knows(monkeypatch, {"психо": Origin(title="Psycho", year=1960)})

    _plans, said = _search(client, "психо", monkeypatch)

    assert "по справке" not in said
    assert "добрал по «Psycho»" in said


def test_a_latin_named_picture_without_an_article_keeps_its_translit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Смежный класс: у латинописанного аниме статьи в русской Википедии нет вовсе.

    «Врата Штейна» подписаны латиницей (``Steins;Gate``), русской статьи под этим именем
    нет, и справка молчит по-честному. Транслит для такой картины - единственное, что
    есть, и отнимать его нельзя: на нём и стоит весь добор.
    """
    client = _FakeProwlarr(
        {
            "врата штейна": [raw("Врата Штейна (2011) WEB-DL", 1)],
            "vrata shteyna": [
                raw(f"Vrata Shteyna Steins Gate 2011 BDRip {i}", 10 + i) for i in range(6)
            ],
        }
    )
    _knows(monkeypatch, {})  # статьи нет - паспорт пуст

    _plans, said = _search(client, "врата штейна", monkeypatch)

    assert client.asked == ["врата штейна", "vrata shteyna"]
    assert "по справке" not in said
    assert "добрал по «vrata shteyna»: стало 7" in said


def test_a_query_typed_in_the_wrong_layout_reads_as_russian() -> None:
    """🔴 TC-195. `nfxrb` - это «тачки» клавиша в клавишу, а не транслит."""
    assert unswap_layout("nfxrb") == "тачки"
    assert unswap_layout("rjhgjhfwbz vjycnhjd") == "корпорация монстров"
    assert unswap_layout("NFXRB") == "тачки"


def test_the_layout_swap_keeps_digits_and_spacing() -> None:
    """Номер части в новой строке остаётся номером: «nfxrb 2» → «тачки 2»."""
    assert unswap_layout("nfxrb 2") == "тачки 2"


def test_the_wrong_layout_finds_the_picture_instead_of_refusing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-195. Ровно первая строка вечера владельца: `cast nfxrb` вместо «cast тачки».

    Прежде это был отказ «по запросу «nfxrb» ничего не нашлось» за 1.8 с при живом
    каталоге. Откат правки роняет тест на ``NotFoundError``.
    """
    client = _FakeProwlarr(
        {"тачки": [raw(f"Тачки / Cars (2006) BDRip 1080p {i}", i) for i in range(20)]}
    )

    plans, said = _search(client, "nfxrb", monkeypatch)

    assert client.asked == ["nfxrb", "тачки"]
    assert plans[0].picture.title.casefold().startswith("тачки")
    # Подмена не молчаливая: человек читает, что за него прочитали.
    assert "в русской раскладке" in said


def test_a_latin_query_that_finds_something_is_never_re_read_as_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«cars» находит своё, и второго захода («сфкы») не случается вовсе - ни секунды."""
    client = _FakeProwlarr(
        {"cars": [raw(f"Cars.2006.1080p.BluRay.x264-GRP{i}", i) for i in range(20)]}
    )

    _plans, said = _search(client, "cars", monkeypatch)

    assert client.asked == ["cars"]
    assert "раскладке" not in said


def test_a_picture_dubbed_only_in_unplayable_releases_is_asked_by_original_and_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-210. «Тачки»: по-русски одни образы DVD, играбельное - англоязычный рип.

    Живая выдача первой части: все русские раздачи оказались DVD-образами (играть в них
    нечего, и отбор не берёт их по делу), а единственным кандидатом остаётся
    ``Cars 2006 BluRay 1080p`` на 66 сид - без русской дорожки. Добор вторым языком сюда
    уже сходил и принёс ровно его: по слову ``Cars`` индексер отдаёт первую сотню строк,
    и русского ``BDRip 1080p | D`` в ней нет.

    Разводит эту сотню ГОД: точная строка ``Cars 2006`` приносит «Тачки / Cars (2006)
    BDRip 1080p | D» на 61 сид - честный 1080p с дубляжом и вчетверо легче образа диска.
    """
    _knows(monkeypatch, {"тачки": Origin(title="Cars", year=2006, name="Тачки")})
    client = _FakeProwlarr(
        {
            "тачки": [
                raw(f"Тачки / Cars [2006, США, мультфильм, DVD9] дубляж {i}", i, seeders=4)
                for i in range(3)
            ],
            "cars": [raw("Cars 2006 BluRay 1080p DDP 5 1 x264-hallowed", 10, seeders=66)],
            "cars 2006": [
                raw("Тачки / Cars (2006) BDRip 1080p | D", 20, seeders=61, size=4.4 * GB)
            ],
        }
    )

    plans, said = _search(client, "тачки", monkeypatch)

    assert client.asked == ["тачки", "Cars", "Cars 2006"]
    assert "«Тачки» по-русски есть только там, где играть нечем - добрал по «Cars 2006»" in said
    top = plans[0].ranked[0]
    assert top.dubbed, "верхом стоит раздача с русской дорожкой, а не англоязычный рип"
    assert "BDRip 1080p | D" in top.raw_name


def test_a_dub_locked_behind_the_bitrate_ceiling_is_asked_by_original_and_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-211. «Тачки 2»: дубляж обещан только 4К-ремуксом, который отбор не берёт.

    Кандидатом у второй части стоит ремукс на 27 ГБ, о звуке молчащий, а дубляж назван в
    38-гигабайтном 2160p - и тот не проходит потолок битрейта (:func:`over_ceiling`)
    задолго до всякого ffprobe. Отказывать потолком нельзя (ремукс такого веса и правда
    не сыграть), но и вечера по-русски так не выходит.

    Номер части у добора вторым языком отрезан разбором франшизы, поэтому он уходит
    словом ``Cars`` и не приносит ничего. Точная строка собирается по самой картине -
    ``Cars 2 2011``, - и приносит «Тачки 2 / Cars 2 (2011) BDRip 1080p» на 11 сид: пять
    гигабайт, дубляж, никакого сплошного перекода.
    """
    _knows(monkeypatch, {"тачки": Origin(title="Cars", year=2006, name="Тачки")})
    client = _FakeProwlarr(
        {
            "тачки": [
                raw(
                    "Тачки 2 / Cars 2 [2011, США, мультфильм, BDRemux 1080p] "
                    "[Локализованный видеоряд]",
                    1,
                    seeders=71,
                    size=27 * GB,
                ),
                raw(
                    "Тачки 2 / Cars 2 [2011, США, мультфильм, UHD BDRemux 2160p, HDR10] "
                    "Dub + Ukr + Original (Eng)",
                    2,
                    seeders=126,
                    size=38 * GB,
                ),
            ],
            "cars 2 2011": [
                raw(
                    "Тачки 2 / Cars 2 (2011) BDRip 1080p от Leonardo and Scarabey-Лицензия",
                    3,
                    seeders=11,
                    size=5.3 * GB,
                )
            ],
        }
    )

    plans, said = _search(client, "тачки 2", monkeypatch)

    assert client.asked == ["тачки", "Cars", "Cars 2 2011"]
    assert "«Тачки 2» по-русски есть только там, где играть нечем" in said
    top = plans[0].ranked[0]
    assert top.dubbed and top.height == 1080, "верх - честный 1080p с дубляжом"
    assert "Leonardo" in top.raw_name
