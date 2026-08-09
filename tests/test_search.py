"""Разбор выдачи Prowlarr: JSON ``/api/v1/search`` и Torznab-RSS.

Фикстуры — куски живой выдачи (Prowlarr 2.5.2, индексеры Knaben и RuTor),
плюс дописанные вручную битые строки: без ``infoHash``, с пустым именем и с
мусором вместо хэша. Все три обязаны молча отсеиваться, а не ронять поиск.
"""

from __future__ import annotations

import json
import threading
import time
from itertools import permutations
from pathlib import Path
from typing import Final

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
    merge,
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


class _Reply:
    """Ответ одного запроса. Отдельным объектом, а не полем сессии: индексеры теперь
    спрашиваются каждый своим потоком, и общее поле payload они бы затирали друг у друга."""

    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class _UnavailableReply(_Reply):
    text = "All selected indexers being unavailable"

    def raise_for_status(self) -> None:
        import requests

        response = requests.Response()
        response.status_code = 400
        response._content = self.text.encode()
        raise requests.HTTPError("400 Client Error", response=response)


class _Swarm:
    """Prowlarr с четырьмя индексерами, из которых один умеет молчать до бюджета."""

    def __init__(
        self,
        mute: int | None = None,
        mute_all: bool = False,
        rows: int = 1,
        hold: set[int] | None = None,
        yts: bool = False,
    ) -> None:
        self.mute = mute
        self.mute_all = mute_all
        #: Сколько раздач отдаёт один ответивший индексер: одна - пул тощий (сработает
        #: фолбэк по анимешным, TC-229), несколько - пул полный, и фолбэку нечего добавить.
        self.rows = rows
        #: Кого держим до отмашки: так изображается опоздавший, не выдумывая секунд.
        #: Отмашки нет до конца бюджета - индексер молчит, как молчал бы живой.
        self.hold = hold or set()
        self.gate = threading.Event()
        #: Включён ли YTS. По умолчанию нет: у него личный короткий бюджет (TC-213), и
        #: остальным тестам круга это только мешало бы.
        self.yts = yts
        self.urls: list[str] = []
        self.waited: list[float] = []
        #: Бюджет, с которым спросили каждого: списками этого не собрать - запросы идут
        #: из разных потоков, и два параллельных списка разъезжаются между собой.
        self.budget: dict[str, float] = {}

    def get(self, url: str, timeout: float) -> _Reply:
        import requests

        self.urls.append(url)
        self.waited.append(timeout)
        if url.endswith("/api/v1/indexer?apikey=KEY"):
            return _Reply(
                [
                    {"id": 1, "name": "Knaben", "enable": True},
                    {"id": 2, "name": "RuTor", "enable": True},
                    {"id": 3, "name": "Nyaa.si", "enable": True},
                    {"id": 4, "name": "YTS", "enable": self.yts},
                ]
            )
        num = int(url.rsplit("&indexerIds=", 1)[1])
        self.budget[str(num)] = timeout
        if self.mute_all or num == self.mute:
            raise requests.ConnectTimeout("молчит")
        if num in self.hold and not self.gate.wait(timeout):
            raise requests.ConnectTimeout("молчит")
        return _Reply(self._rows(num))

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


def test_prowlarr_400_names_unavailable_indexers_not_prowlarr() -> None:
    """Особый 400 означает, что Prowlarr жив, а отказали выбранные индексеры."""
    client = _swarm()
    session = client._session
    original = session.get  # type: ignore[union-attr]

    def unavailable(url: str, **kwargs: object) -> _Reply:
        if "/api/v1/search" in url:
            return _UnavailableReply([])
        reply: _Reply = original(url, **kwargs)  # type: ignore[arg-type,assignment]
        return reply

    session.get = unavailable  # type: ignore[union-attr,method-assign]
    with pytest.raises(InfraError) as caught:
        client.search("матрица")
    message = str(caught.value)
    assert message == "индексеры не отвечают: Knaben, RuTor"
    assert "Prowlarr не отвечает" not in message


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


def test_yts_asked_in_its_own_short_budget() -> None:
    """🔴 TC-213: у YTS бюджет свой и короткий, у остальных - общий.

    Терять на нём нечего: замер TC-141 дал +2.1% к пулу и ноль запросов, где он
    единственный источник играбельного HD. А платили мы за него полным бюджетом:
    его выдачу рвёт канал на объёме тела, и молчание выбирало все 20 с (замер на
    стенде: «barbie» - 20.02 с). Честный ответ у него - 0.5-0.9 с.
    """
    from torrcast.search import _EXTRA_TIMEOUT, _QUORUM_TIMEOUT, _SHORT_TIMEOUT, indexer_budget

    client = _swarm(yts=True, rows=2)
    client.search("barbie 2023")  # латиница с годом - не аниме, Nyaa вне круга
    budget = client._session.budget  # type: ignore[union-attr]
    assert budget == {"1": _QUORUM_TIMEOUT, "2": _QUORUM_TIMEOUT, "4": _SHORT_TIMEOUT}
    assert _SHORT_TIMEOUT < _EXTRA_TIMEOUT, "короткий бюджет обязан быть заметно короче"
    # Судим по имени, а не по номеру: номер у индексера свой на каждой установке.
    # Короткий список только УРЕЗАЕТ роль (TC-226): YTS некворумный, его потолок и так
    # десять секунд, а короткий бюджет опускает до шести.
    assert indexer_budget("YTS") == _SHORT_TIMEOUT
    assert indexer_budget("Knaben") == _QUORUM_TIMEOUT
    assert indexer_budget("Nyaa.si") == _EXTRA_TIMEOUT


def test_silent_yts_costs_only_its_short_budget() -> None:
    """Молчащий YTS не держит круг общим бюджетом: и отметка называет его цену честно."""
    from torrcast.search import _SHORT_TIMEOUT

    client = _swarm(yts=True, rows=2, mute=4)
    results = client.search("barbie 2023")
    assert [r.indexer for r in results] == ["idx.1", "idx.1", "idx.2", "idx.2"]
    assert client.silent == ("YTS",)
    assert client._session.budget["4"] == _SHORT_TIMEOUT  # type: ignore[union-attr]


def test_show_survives_when_nyaa_is_silent_in_fallback() -> None:
    """Деградация: Nyaa недоступен на фолбэке - его имя уходит в молчуны, находки
    остальных доезжают, показ не ломается."""
    client = _swarm(mute=3)  # тощий пул -> фолбэк зовёт Nyaa, а тот молчит
    results = client.search("матрица")
    assert [r.title for r in results] == ["picture.1", "picture.2"]
    assert client.silent == ("Nyaa.si",)


def test_круг_уходит_по_кворуму_не_дожидаясь_остальных() -> None:
    """🔴 TC-118: круг возвращается, когда ответил кворум (Knaben + RuTor), а не когда
    отговорили все четверо. Опоздавший (Nyaa) в этот момент ещё держит соединение - и
    раньше держал бы вместе с ним всё меню, до своего полного бюджета в 20 с."""
    client = _swarm(rows=2, hold={3})  # Nyaa не отпустят до отмашки
    results = client.search("Naruto [TV]")  # аниме-запрос: Nyaa в основном круге
    assert len(results) == 4  # Knaben и RuTor по две раздачи, Nyaa не дождались
    assert client.silent == ()  # опоздавший - не молчун: он ещё в пути


def test_опоздавший_доливается_после_круга_а_не_теряется() -> None:
    """Выдача опоздавшего не выбрасывается: она забирается :meth:`Prowlarr.late` уже
    после того, как список показан. Пока индексер в пути, долив пуст - ждать его на
    пути до меню и значило бы не уходить по кворуму."""
    client = _swarm(rows=2, hold={3})
    client.search("Naruto [TV]")
    assert client.late() == []  # ещё в пути - долив ничего не обещает
    client._session.gate.set()  # type: ignore[union-attr]
    late = client.late(wait=5.0)
    assert len(late) == 2  # доехали ровно раздачи Nyaa
    assert client.late() == []  # долив разовый: второй раз брать нечего


def test_кворумного_индексера_круг_всё_же_дожидается() -> None:
    """Кворум - это Knaben и RuTor: без них выдачи нет, и ждать их приходится. Отпустим
    RuTor с задержкой - его раздачи обязаны попасть в тот же круг, а не в долив."""
    client = _swarm(rows=2, hold={2})  # RuTor из кворума
    threading.Timer(0.2, client._session.gate.set).start()  # type: ignore[union-attr]
    results = client.search("Naruto [TV]")
    assert len(results) == 6  # все трое: круг дождался кворумного
    assert client.late() == []  # опоздавших нет вовсе


def test_круг_без_кворумных_ждёт_всех() -> None:
    """Фолбэк по анимешным (TC-229) идёт без кворумных вовсе - ждать в нём некого,
    поэтому такой круг дожидается всех спрошенных. Иначе он возвращался бы пустым."""
    client = _swarm(hold={3})  # rows=1: пул тощий, фолбэк зовёт Nyaa
    threading.Timer(0.2, client._session.gate.set).start()  # type: ignore[union-attr]
    results = client.search("матрица")
    assert [r.title for r in results] == ["picture.1", "picture.2", "picture.3"]


def test_кворумного_ждём_дольше_остальных() -> None:
    """🔴 TC-226. Хвост поиска - это Knaben: 502 через 10-15 с плюс ретрай Prowlarr.
    Резать его личным бюджетом в 3-5 с нельзя - он несёт 41% каталога, и замер дал
    1 подмену дефолта и 7 подмен верхнего релиза на 100 запросов. Поэтому кворумному
    бюджет остаётся полным, а короткий достаётся тем, кого круг и так не ждёт."""
    client = _swarm(rows=2)
    client.search("Naruto [TV]")
    budget = client._session.budget  # type: ignore[union-attr]
    assert budget["1"] == budget["2"] == 20.0, "Knaben и RuTor - кворум, их ждём дольше"
    assert budget["3"] == 10.0, "Nyaa круг не ждёт: его бюджет - цель пути, а не молчание"


def test_второй_круг_идёт_в_остаток_цели() -> None:
    """🔴 TC-228. Первый круг - это и есть поиск, у него личные бюджеты. А каждый
    следующий (добор вторым языком, сезонная строка, чтение раскладки) платит из остатка
    цели: раньше он платил хвост первого круга ПЛЮС свой полный, и на хвосте Knaben это
    давало 30 с при цели в 10."""
    client = _swarm(rows=2)
    client.search("Naruto [TV]")
    assert client._session.budget["1"] == 20.0  # type: ignore[union-attr]
    client._began = time.monotonic() - 8.0  # изобразим поиск, съевший 8 секунд цели
    client.search("Naruto [TV]")
    budget = client._session.budget  # type: ignore[union-attr]
    assert 1.5 < budget["1"] <= 2.0, "кворумному во втором круге - ровно остаток цели"
    assert budget["3"] <= 2.0, "и некворумному тоже: цель у поиска одна на всех"


def test_огрызок_бюджета_доводится_до_секунды() -> None:
    """Цель съедена целиком, а спрашивать всё-таки идём (пустая выдача, чтение забытой
    раскладки) - тогда круг спрашивается хотя бы на секунду. Круг с нулевым бюджетом это
    не экономия, а гарантированный молчун ценой в лишний запрос к трекеру."""
    client = _swarm(rows=2)
    client.search("Naruto [TV]")
    client._began = time.monotonic() - 30.0  # цели не осталось вовсе
    assert client.spare() == 0.0
    client.search("Naruto [TV]")
    assert client._session.budget["1"] == 1.0  # type: ignore[union-attr]


def test_след_отличает_опоздавшего_от_молчуна(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Опоздавший и молчун - разные причины хвоста, и в следе они врозь: иначе `cast log`
    объяснял бы задержку кругом, которого не было."""
    from torrcast import trace

    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path))
    monkeypatch.setenv(trace.SID_ENV, "test-sid")
    client = _swarm(rows=2, hold={3})
    client.search("Naruto [TV]")
    trace.shutdown()
    (row,) = [r for r in trace.records() if r.get("event") == "indexers"]
    assert row["late"] == ["Nyaa.si"]
    assert row["silent"] == []
    assert "опоздали Nyaa.si" in trace.digest(trace.records())


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


def _mirror(title: str, seeders: int, indexer: str, size: int = 8_000_000_000) -> RawResult:
    """Одна и та же раздача глазами разных индексеров: hash общий, данные врозь."""
    return RawResult(title=title, info_hash="a" * 40, size=size, seeders=seeders, indexer=indexer)


#: Живой случай с сырых пулов: один индексер видит у раздачи 2 сида, другой 26, третий
#: зовёт её иначе. До TC-239 в выдачу шла строка того, кто ответил первым.
_ONE_TORRENT: Final = (
    _mirror("Дюна: Пророчество / Dune: Prophecy (2024) WEB-DL 1080p", 2, "Knaben"),
    _mirror("Дюна: Пророчество / Dune: Prophecy (2024) WEB-DL 1080p", 26, "RuTor", 8_000_000_512),
    _mirror("Dune Prophecy S01 2024 1080p WEB-DL", 9, "Nyaa.si", 8_000_001_024),
)


def test_склейка_не_зависит_от_порядка_прихода_индексеров() -> None:
    """Кто ответил первым - дело сети, а не каталога: строка раздачи обязана совпасть
    при любом порядке ответов, иначе на телевизор едет то один файл, то другой.
    """
    snapshots = {
        tuple(
            (row.title, row.seeders, row.size, row.indexer, row.copies)
            for row in merge(*([item] for item in order))
        )
        for order in permutations(_ONE_TORRENT)
    }
    assert len(snapshots) == 1


def test_склейка_берёт_максимум_сидов_и_имя_по_большинству() -> None:
    """Рой у раздачи ОДИН - расхождение в сидах это разное время скрейпа, поэтому цифра
    берётся самая свежая. Имя - по большинству, тем же правилом, что у канона картины:
    оно не обязано приехать той же строкой, что и максимум сидов.
    """
    (merged,) = merge(*([item] for item in _ONE_TORRENT))
    assert merged.seeders == 26
    assert merged.title == "Дюна: Пророчество / Dune: Prophecy (2024) WEB-DL 1080p"
    assert merged.copies == 3  # сколько РАЗНЫХ индексеров привезли раздачу - счёт прежний


def test_склейка_разводит_ничью_имён_короче_и_по_алфавиту() -> None:
    """Двое индексеров - обычное дело, и большинства там не бывает. Ничья разводится
    так же, как в кластеризации, а не по тому, чей ответ приехал раньше.
    """
    pair = (_mirror("Психо", 5, "Knaben"), _mirror("Psycho", 7, "RuTor"))
    names = {merge(*([item] for item in order))[0].title for order in permutations(pair)}
    assert names == {"Психо"}
