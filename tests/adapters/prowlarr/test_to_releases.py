"""Проверяет перевод сырых строк в релизы: имя разобрано, поля каталога при них."""

import json
from pathlib import Path

import pytest

from torrcast.adapters.prowlarr.from_json import from_json
from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.raw_result import RawResult

FIXTURES = Path(__file__).parents[2] / "fixtures"


@pytest.fixture(scope="module")
def json_results() -> list[RawResult]:
    return from_json(json.loads((FIXTURES / "prowlarr_search.json").read_text(encoding="utf-8")))


def test_to_releases_parses_names_and_keeps_source_fields(
    json_results: list[RawResult],
) -> None:
    releases = to_releases(json_results)
    # Подзаголовок сборника отрезается парсером: «Матрица. Квадрология» → «Матрица».
    assert [r.title for r in releases] == ["Матрица", "Матрица"]
    assert releases[0].year == 1999
    assert releases[0].quality == "1080p"
    assert releases[0].magnet.startswith("magnet:?xt=urn:btih:")
    assert [r.size for r in releases] == [r.size for r in json_results]
    assert [r.indexer for r in releases] == ["Knaben", "RuTor"]


def test_склеенные_имена_и_индексеры_доезжают_до_релиза() -> None:
    """Признаки читаются по ВСЕМ строкам раздачи, поэтому склеенное едет целиком."""
    row = RawResult(
        title="Матрица (1999) 1080p",
        info_hash="a" * 40,
        size=1,
        seeders=2,
        indexer="Knaben",
        copies=3,
        indexers=("Knaben", "Nyaa.si"),
        names=("Матрица (1999) 1080p", "The Matrix 1999 1080p"),
    )
    (release,) = to_releases([row])
    assert release.indexers == ("Knaben", "Nyaa.si")
    assert release.names == ("Матрица (1999) 1080p", "The Matrix 1999 1080p")
    assert release.copies == 3


def test_пустая_выдача_даёт_пустой_список() -> None:
    assert to_releases([]) == []


def test_n1_n4_не_видео_раздача_не_доходит_до_релизов() -> None:
    """Отсев не-видео (N1-N4) стоит именно на этой границе, до кластеризации."""
    row = RawResult(
        title="Семнадцать мгновений весны / Михаил Таривердиев OST (1973) APE by гаврила",
        info_hash="b" * 40,
    )
    assert to_releases([row]) == []


def test_видео_раздача_с_вето_приметой_доходит_до_релизов() -> None:
    row = RawResult(
        title="Oppenheimer 2023 REPACK 1080p BluRay DD 5 1 x264-PTer",
        info_hash="c" * 40,
    )
    assert [r.title for r in to_releases([row])] == ["Oppenheimer"]


def test_вид_немой_раздачи_берётся_у_соседки_по_той_же_выдаче() -> None:
    """🔴 TC-854. Перевод выдачи достраивает вид по ВСЕМ строкам разом.

    Имя `[Trix] Cyberpunk: Edgerunners (2022)` не несёт ни сезона, ни номера серии, и
    разбор в одиночку зовёт его фильмом - а у картины вида «фильм» очереди серий нет по
    построению, и показ берёт крупнейший файл. Соседка по той же выдаче названа сезоном
    явно, и вид берётся у неё. Проводка стоит именно тут: дальше выдачу разносит по
    картинам ``cluster``, и ключ картины начинается с вида.
    """
    mute = RawResult(
        title="[Trix] Cyberpunk: Edgerunners (2022) [Optional Dual Audio] (720p AV1)",
        info_hash="d" * 40,
    )
    named = RawResult(
        title="Киберпанк: Бегущие по краю / Cyberpunk: Edgerunners [S01] (2022) BDRip",
        info_hash="e" * 40,
    )
    (alone,) = to_releases([mute])
    assert alone.kind == "movie", "занять вид не у кого - вид прежний"
    together = to_releases([mute, named])
    assert [r.kind for r in together] == ["tv", "tv"], "вид берётся у соседки с сезоном"


def test_догадка_соседки_по_голому_диапазону_вида_не_одалживает() -> None:
    """🔴 Соседка, чей вид угадан диапазоном, права голоса не имеет.

    `Форсаж 1-6. Коллекция` разбирается сериалом по голому диапазону при ``season=None``.
    Порога между ним и `Nanatsu no Taizai OVA [1-2]` замером не найдено, и разносить
    чужую догадку по франшизе нельзя.
    """
    guessed = RawResult(
        title="Форсаж 1-6. Коллекция / The Fast And The Furious 1-6. Collection (2001-2013) BDRip",
        info_hash="f" * 40,
    )
    part = RawResult(
        title="The Fast and The Furious Collection [2001-2023] BluRay HEVC x265 10Bit DTS",
        info_hash="0" * 40,
    )
    kinds = {r.raw_name: r.kind for r in to_releases([part, guessed])}
    assert kinds[part.title] == "movie", "франшиза не красится чужой догадкой"


def test_вид_сборника_берётся_у_соседки_а_не_у_буквы_в_его_имени() -> None:
    """🔴 TC-1033. `Rome 1-5` остаётся сериалом законно - соседкой, а не буквой `e`.

    В самих именах признака нет: `Rome 1-5` и `Ice Age 1-5` устроены одинаково, и
    буква `e` перед диапазоном есть у обоих. Разводит их ВЫДАЧА источника, и обе
    строки ниже взяты из снятой выдачи Prowlarr: по запросу «Rome» приезжает
    `Рим / Rome [S01-02] (2005)`, чей сезон назван явно и чей год не спорит, а по
    «Ice Age» ни одна раздача с явным сезоном картину `Ice Age` не зовёт - две
    нашедшиеся про `Ice Age Giants`, и это другая картина.
    """
    rome = RawResult(title="Rome 1-5 (2005) BDRip", info_hash="1" * 40)
    rome_named = RawResult(title="Рим / Rome [S01-02] (2005-2007) BDRip-Пучков", info_hash="2" * 40)
    ice = RawResult(title="Ice Age 1-5 (2002-2016) BDRip 1080p", info_hash="3" * 40)
    ice_named = RawResult(
        title="BBC: Гиганты ледникового периода / Ice Age Giants [S01] (2013) HDTV 720p",
        info_hash="4" * 40,
    )

    said = {r.raw_name: r.kind for r in to_releases([rome, rome_named])}
    silent = {r.raw_name: r.kind for r in to_releases([ice, ice_named])}

    assert said[rome.title] == "tv", "о сборнике сказала соседка с явным сезоном"
    assert silent[ice.title] == "movie", "об этой картине не сказал никто - сборник фильмов"
