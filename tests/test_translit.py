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
from torrcast.parse import THIN_POOL, Picture, Release, alt_query, parse_release_name, transliterate
from torrcast.search import RawResult, merge
from torrcast.state import Config

GB = 1024**3


def _knows(monkeypatch: pytest.MonkeyPatch, passports: dict[str, Origin]) -> list[str]:
    """Подложить справке готовые паспорта и записывать, о чём её спрашивали."""
    asked: list[str] = []

    def about(title: str, series: bool = False) -> Origin:
        asked.append(title)
        return passports.get(title, Origin())

    monkeypatch.setattr(cli, "origin", about)
    return asked


def raw(name: str, number: int, seeders: int = 100) -> RawResult:
    """Строка выдачи: hash различает раздачи, по нему же они и склеиваются."""
    return RawResult(
        title=name, info_hash=f"{number:040x}", size=int(8 * GB), seeders=seeders, indexer="Knaben"
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


def test_alt_query_is_empty_for_a_latin_request() -> None:
    """Спросили латиницей - добирать нечем, второго захода не бывает."""
    assert alt_query("psycho", [ru("Психо / Psycho (1960) DVDRip")]) == ""


def test_merge_keeps_each_torrent_once_and_holds_the_order() -> None:
    first, second = [raw("Психо", 1), raw("Психо", 2)], [raw("Psycho", 2), raw("Psycho", 3)]
    merged = merge(first, second)
    assert [r.title for r in merged] == ["Психо", "Психо", "Psycho"]


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


def _catalog(russian: int, latin: int) -> _FakeProwlarr:
    """«Психо»: по-русски пара DVDRip'ов, на латинице - весь каталог в 1080p."""
    return _FakeProwlarr(
        {
            "психо": [raw(f"Психо / Psycho (1960) DVDRip {i}", i) for i in range(russian)],
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
    """Счастливый путь не платит за чужую беду: полная выдача - один запрос."""
    client = _catalog(russian=THIN_POOL, latin=40)
    plans, _said = _search(client, "психо", monkeypatch)

    assert client.asked == ["психо"]
    assert len(plans[0].picture.releases) == THIN_POOL


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


def test_a_namesake_without_a_part_number_is_still_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Послабление касается ТОЛЬКО запроса с номером: без номера год справки решает."""
    client = _FakeProwlarr(
        {"тачки": [raw(f"Тачки 2 / Cars 2 (2011) BDRip {i}", i) for i in range(3)]}
    )
    _knows(monkeypatch, {"тачки": Origin(title="Cars", year=2006)})

    with pytest.raises(NotFoundError):
        _search(client, "тачки", monkeypatch)


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
    client = _catalog(russian=THIN_POOL, latin=40)
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


def test_the_reference_original_does_not_open_the_gate_to_another_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Оригинал из справки - proven, но год всё равно сверяется.

    Имя пришло от справки, значит оно про ту самую картину; а вот приехать по нему может
    чужое кино того же названия. Год расходится - добора не было, и это честное
    «не нашлось», а не чужой фильм.
    """
    client = _FakeProwlarr(
        {
            "the ascent": [
                raw(f"The.Climbers.2019.1080p.WEB-DL.x264-{i}", i) for i in range(20)
            ]
        }
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
