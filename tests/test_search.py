"""Разбор выдачи Prowlarr: JSON ``/api/v1/search`` и Torznab-RSS.

Фикстуры — куски живой выдачи (Prowlarr 2.5.2, индексеры Knaben и RuTor),
плюс дописанные вручную битые строки: без ``infoHash``, с пустым именем и с
мусором вместо хэша. Все три обязаны молча отсеиваться, а не ронять поиск.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from torrcast import InfraError, NotFoundError
from torrcast.search import (
    PUBLIC_TRACKERS,
    Prowlarr,
    RawResult,
    anime_query,
    from_json,
    from_torznab,
    magnet_for,
    to_releases,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def json_results() -> list[RawResult]:
    return from_json(json.loads((FIXTURES / "prowlarr_search.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def xml_results() -> list[RawResult]:
    return from_torznab((FIXTURES / "torznab.xml").read_text(encoding="utf-8"))


def test_json_keeps_only_usable_rows(json_results: list[RawResult]) -> None:
    """Из пяти строк фикстуры пригодны только две: у остальных нет хэша или имени."""
    assert [r.indexer for r in json_results] == ["Knaben", "RuTor"]


def test_json_carries_size_and_seeders(json_results: list[RawResult]) -> None:
    first = json_results[0]
    assert first.size > 0
    assert first.seeders >= 0
    assert first.info_hash == "E79011C658D37DB16880EB414097920250564DC3"


def test_torznab_reads_infohash_from_attr(xml_results: list[RawResult]) -> None:
    """infohash и seeders в Torznab лежат не в тегах, а в ``torznab:attr``."""
    assert len(xml_results) == 3  # четвёртый item - без infohash
    assert all(len(r.info_hash) == 40 for r in xml_results)
    assert all(r.indexer == "Knaben" for r in xml_results)
    assert any(r.seeders > 0 for r in xml_results)


def test_torznab_rejects_broken_xml() -> None:
    with pytest.raises(InfraError, match="битый XML"):
        from_torznab("<rss><channel><item>")


def test_json_rejects_non_list() -> None:
    with pytest.raises(InfraError, match="неожиданный ответ"):
        from_json({"error": "нет"})


def test_magnet_has_hash_name_and_trackers() -> None:
    """magnetUrl у Prowlarr — прокси-ссылка, поэтому magnet собираем сами."""
    magnet = magnet_for("ABCdef0123456789ABCDEF0123456789abcdef01", "Тачки 3")
    assert magnet.startswith("magnet:?xt=urn:btih:abcdef0123456789abcdef0123456789abcdef01")
    assert "dn=%D0%A2%D0%B0%D1%87%D0%BA%D0%B8%203" in magnet
    assert magnet.count("&tr=") == len(PUBLIC_TRACKERS)


def test_magnet_without_title_has_no_dn() -> None:
    assert "dn=" not in magnet_for("0" * 40)


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


class _FakeSession:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.url = ""

    def get(self, url: str, timeout: float) -> _FakeSession:
        self.url = url
        return self

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


def _client(payload: object) -> Prowlarr:
    client = Prowlarr("http://127.0.0.1:9696/", "KEY")
    client._session = _FakeSession(payload)  # type: ignore[assignment]
    return client


def test_search_builds_expected_url() -> None:
    """Эндпоинт у Jackett и Prowlarr разный; наш клиент ходит в /api/v1/search."""
    client = _client(json.loads((FIXTURES / "prowlarr_search.json").read_text(encoding="utf-8")))
    client.search("матрица")
    url = client._session.url  # type: ignore[union-attr]
    assert url.startswith("http://127.0.0.1:9696/api/v1/search?apikey=KEY")
    assert "&type=search" in url
    assert "&categories=2000&categories=5000&categories=8000" in url


def test_search_reports_empty_result_as_not_found() -> None:
    with pytest.raises(NotFoundError, match="ничего не нашлось"):
        _client([]).search("нетакогофильма")


def _row(name: str, tag: str) -> dict[str, object]:
    """Одна строка выдачи: хэш подделываем из тега, чтобы раздачи не склеились."""
    return {
        "title": name,
        "infoHash": tag * 40,
        "size": 1024,
        "seeders": 5,
        "indexer": name.split(".")[0],
    }


class _Swarm:
    """Prowlarr с четырьмя индексерами, из которых один умеет молчать до бюджета."""

    def __init__(self, mute: int | None = None, mute_all: bool = False, rows: int = 1) -> None:
        self.mute = mute
        self.mute_all = mute_all
        #: Сколько раздач отдаёт один ответивший индексер: одна - пул тощий (сработает
        #: фолбэк по анимешным, TC-229), несколько - пул полный, и фолбэку нечего добавить.
        self.rows = rows
        self.urls: list[str] = []
        self.waited: list[float] = []
        self.payload: object = []

    def get(self, url: str, timeout: float) -> _Swarm:
        import requests

        self.urls.append(url)
        self.waited.append(timeout)
        if url.endswith("/api/v1/indexer?apikey=KEY"):
            self.payload = [
                {"id": 1, "name": "Knaben", "enable": True},
                {"id": 2, "name": "RuTor", "enable": True},
                {"id": 3, "name": "Nyaa.si", "enable": True},
                {"id": 4, "name": "YTS", "enable": False},
            ]
            return self
        num = int(url.rsplit("&indexerIds=", 1)[1])
        if self.mute_all or num == self.mute:
            raise requests.ConnectTimeout("молчит")
        self.payload = self._rows(num)
        return self

    def _rows(self, num: int) -> list[dict[str, object]]:
        """Выдача одного индексера: при ``rows == 1`` - ровно одна строка (как было),
        иначе несколько строк с разными хэшами, чтобы :func:`merge` их не склеил."""
        if self.rows == 1:
            return [_row(f"picture.{num}", str(num))]
        return [
            {
                "title": f"picture.{num}.{k}",
                "infoHash": f"{num:x}{k:x}".ljust(40, "0"),
                "size": 1024,
                "seeders": 5,
                "indexer": f"idx.{num}",
            }
            for k in range(self.rows)
        ]

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


def _swarm(**kwargs: object) -> Prowlarr:
    client = Prowlarr("http://127.0.0.1:9696/", "KEY")
    client._session = _Swarm(**kwargs)  # type: ignore[assignment,arg-type]
    return client


def test_search_asks_every_indexer_apart() -> None:
    """Врозь - значит по запросу на индексер, и выключенный не спрашиваем вовсе."""
    client = _swarm()
    results = client.search("матрица")
    urls = client._session.urls  # type: ignore[union-attr]
    assert [u.rsplit("=", 1)[1] for u in urls if "&indexerIds=" in u] == ["1", "2", "3"]
    assert [r.title for r in results] == ["picture.1", "picture.2", "picture.3"]
    assert client.silent == ()


def test_silent_indexer_costs_only_its_own_budget() -> None:
    """Молчун не забирает выдачу остальных: она приезжает, а его имя названо.

    Это и есть цена залипания: раньше один молчащий индексер держал общий запрос до
    сотой секунды, и меню ждали 100 с вместе с уже готовыми находками трёх других.
    """
    client = _swarm(mute=2)
    results = client.search("матрица")
    assert [r.title for r in results] == ["picture.1", "picture.3"]
    assert client.silent == ("RuTor",)
    # Личный бюджет молчуна - не общий потолок: 20 с против 150.
    assert max(client._session.waited) < client.timeout  # type: ignore[union-attr]


def test_trace_carries_per_indexer_milliseconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Событие круга несёт время КАЖДОГО индексера - и ответившего, и молчуна.

    Замер наш, на месте вызова: elapsedTime истории Prowlarr врёт про провалившиеся
    и повторные попытки, и хвост круга (кто и сколько держал) без своего секундомера
    из следа не разобрать (TC-230).
    """
    from torrcast import trace

    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path))
    monkeypatch.setenv(trace.SID_ENV, "test-sid")
    client = _swarm(mute=2)
    client.search("матрица")
    trace.shutdown()
    (row,) = [r for r in trace.records() if r.get("event") == "indexers"]
    took = row["ms"]
    assert set(took) == {"Knaben", "RuTor", "Nyaa.si"}
    assert all(isinstance(ms, int) and ms >= 0 for ms in took.values())


def test_all_indexers_silent_is_infra_not_empty_result() -> None:
    """Молчат все до одного - это отказ инфраструктуры, а не «ничего не нашлось»."""
    with pytest.raises(InfraError, match="не отвечает"):
        _swarm(mute_all=True).search("матрица")


def test_anime_query_reads_a_cheap_signal() -> None:
    """«Похоже на аниме» - дешёвый признак, две проверки: прямые слова про аниме или
    латиница без кино-маркеров. При сомнении зовём - полноту аниме ронять нельзя (TC-229)."""
    # Прямые слова аниме - хоть по-русски, хоть латиницей: японские жанры, OVA, метка [TV].
    assert anime_query("боруто аниме")
    assert anime_query("Naruto [TV]")
    assert anime_query("Steins Gate OVA")
    # Латиница без кино-маркеров: оригинальное имя аниме от имени картины не отличить,
    # поэтому сомнение - в пользу вызова.
    assert anime_query("Frieren")
    assert anime_query("Steins Gate")
    # Русскоязычный запрос без аниме-слов: Nyaa на нём молчит, в основной круг не идёт.
    assert not anime_query("матрица")
    assert not anime_query("дюна 2021")
    # Латиница с кино-маркером - год, movie, season, s01: не аниме.
    assert not anime_query("Dune 2021")
    assert not anime_query("Barbie movie")
    assert not anime_query("Breaking Bad season 1")
    assert not anime_query("The Wire s01")


def test_non_anime_query_skips_nyaa_when_pool_is_rich() -> None:
    """🔴 TC-229: явно не-аниме запрос на полном пуле Nyaa не тревожит - тот молчит на
    79% запросов, и лишняя параллель по нему грозит 504-баном Prowlarr на часы."""
    client = _swarm(rows=2)  # Knaben и RuTor дают по две - пул не тощий
    results = client.search("матрица")
    urls = client._session.urls  # type: ignore[union-attr]
    asked = [u.rsplit("=", 1)[1] for u in urls if "&indexerIds=" in u]
    assert asked == ["1", "2"]  # Nyaa (id 3) не спрошен вовсе
    assert client.silent == ()  # неспрошенный - не молчун
    assert len(results) == 4


def test_anime_query_calls_nyaa_in_the_main_circle() -> None:
    """Похожий на аниме запрос зовёт Nyaa сразу, а не фолбэком: пул тут и без него полный,
    так что фолбэк бы не сработал - значит Nyaa именно в основном круге."""
    client = _swarm(rows=2)
    results = client.search("Naruto [TV]")
    asked = [u.rsplit("=", 1)[1] for u in client._session.urls if "&indexerIds=" in u]  # type: ignore[union-attr]
    assert asked == ["1", "2", "3"]  # Nyaa в основном круге
    assert len(results) == 6


def test_thin_pool_falls_back_to_nyaa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Не-аниме запрос, но пул без анимешных вышел тощим - фолбэком зовём и Nyaa.
    В след это событие пишется флагом ``fallback`` (TC-229)."""
    from torrcast import trace

    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path))
    monkeypatch.setenv(trace.SID_ENV, "test-sid")
    client = _swarm()  # rows=1: Knaben + RuTor = две раздачи, ниже порога
    results = client.search("матрица")
    trace.shutdown()
    asked = [u.rsplit("=", 1)[1] for u in client._session.urls if "&indexerIds=" in u]  # type: ignore[union-attr]
    assert asked == ["1", "2", "3"]  # 1 и 2 в основном круге, 3 добран фолбэком
    assert [r.title for r in results] == ["picture.1", "picture.2", "picture.3"]
    (row,) = [r for r in trace.records() if r.get("event") == "indexers"]
    assert row["fallback"] is True


def test_show_survives_when_nyaa_is_silent_in_fallback() -> None:
    """Деградация: Nyaa недоступен на фолбэке - его имя уходит в молчуны, находки
    остальных доезжают, показ не ломается."""
    client = _swarm(mute=3)  # тощий пул -> фолбэк зовёт Nyaa, а тот молчит
    results = client.search("матрица")
    assert [r.title for r in results] == ["picture.1", "picture.2"]
    assert client.silent == ("Nyaa.si",)


def test_wire_query_разводит_склеенные_знаком_слова() -> None:
    """TC-129: Prowlarr вырезает такой знак, не ставя пробела, и в индексер уходит
    несуществующее слово ``SteinsGate`` - ноль строк там, где их 96."""
    from torrcast.parse import wire_query

    assert wire_query("Steins;Gate") == "Steins Gate"
    assert wire_query("Fate/Zero") == "Fate Zero"


def test_wire_query_не_трогает_живые_знаки() -> None:
    """Точка, дефис и апостроф до индексера доезжают целыми, и выдача по ним живая."""
    from torrcast.parse import wire_query

    for query in ("F.R.I.E.N.D.S.", "WALL-E", "Ocean's Eleven", "Fast & Furious", "Amélie"):
        assert wire_query(query) == query


def test_поисковый_url_несёт_запрос_без_склейки() -> None:
    """На проводе - разведённая форма: иначе санитайзер Prowlarr склеит слова."""
    url = Prowlarr("http://p", "k")._url("Steins;Gate", 100)
    assert "query=Steins%20Gate" in url
    assert "%3B" not in url
