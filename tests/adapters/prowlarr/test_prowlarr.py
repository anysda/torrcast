"""Проверяет клиент каталога: круг врозь, бюджеты, баны, долив и отказы.

Подставная сессия изображает Prowlarr 2.5.2 с четырьмя индексерами: кто-то молчит до
бюджета, кто-то отвечает честным нулём, кого-то Prowlarr увёл в недоступные.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from torrcast.adapters.filesystem.trace_journal.records import records
from torrcast.adapters.filesystem.trace_journal.shutdown import shutdown
from torrcast.adapters.prowlarr.indexer_circle import IndexerCircle
from torrcast.adapters.prowlarr.prowlarr import Prowlarr
from torrcast.adapters.prowlarr.prowlarr_http_client import _IndexersUnavailableError
from torrcast.domain.circle_indexers import Indexer
from torrcast.domain.digest.digest import digest
from torrcast.domain.indexer_budget import SHORT_TIMEOUT, indexer_budget
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.raw_result import RawResult
from torrcast.domain.response_budget import LATE_TIMEOUT

FIXTURES = Path(__file__).parents[2] / "fixtures"


class _FakeSession:
    """Одна и та же выдача на любой запрос: список индексеров так не читается."""

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
    client._api.session = _FakeSession(payload)
    return client


def test_search_builds_expected_url() -> None:
    """Эндпоинт у Jackett и Prowlarr разный; наш клиент ходит в /api/v1/search."""
    client = _client(json.loads((FIXTURES / "prowlarr_search.json").read_text(encoding="utf-8")))
    client.search("матрица")
    session = client._api.session
    assert isinstance(session, _FakeSession)
    assert session.url.startswith("http://127.0.0.1:9696/api/v1/search?apikey=KEY")
    assert "&type=search" in session.url
    assert "&categories=2000&categories=5000&categories=6000&categories=8000" in session.url


def test_search_reports_empty_result_as_not_found() -> None:
    with pytest.raises(NotFoundError, match="nothing was found"):
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
    """Ответ одного запроса. Отдельным объектом, а не полем сессии: индексеры
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


def _ago(seconds: float) -> str:
    """Время отказа глазами Prowlarr: UTC с ``Z`` на конце, как на живом стенде."""
    return (datetime.now(UTC) - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Swarm:
    """Prowlarr с четырьмя индексерами, из которых один умеет молчать до бюджета."""

    def __init__(
        self,
        mute: int | None = None,
        mute_all: bool = False,
        rows: int = 1,
        hold: set[int] | None = None,
        yts: bool = False,
        blocked: dict[int, str] | None = None,
        disabled_till: dict[int, str] | None = None,
        refuses: set[int] | None = None,
        empty: set[int] | None = None,
        delay: dict[int, float] | None = None,
        stuck: dict[int, float] | None = None,
        unavailable: bool = False,
    ) -> None:
        #: Кто отвечает ЧЕСТНЫМ нулём: он не молчун и не отказ, просто ничего не нашёл.
        self.empty = empty or set()
        self.delay = delay or {}
        #: Кто залипает дольше круга и отказывает уже после него: номер - сколько секунд
        #: держать запрос. Круг такого не дожидается вовсе, и его ошибка приезжает в
        #: пустую комнату - имя молчуна к этой секунде единственное, что о нём известно.
        self.stuck = stuck or {}
        #: Кого Prowlarr увёл в недоступные: номер - время последнего отказа (UTC).
        #: Пусто - как на здоровом стенде: страница статуса показывает только банных.
        self.blocked = blocked or {}
        self.disabled_till = disabled_till or {}
        #: Кто отказал СЕЙЧАС, до всякого бана (TC-291). Живой замер: источник отвечает
        #: отказом соединения, Prowlarr отдаёт нам ``200 []`` - и в тот же миг заводит
        #: себе отметку об отказе. Ровно это тут и изображается.
        self.refuses = refuses or set()
        #: Отметки, заведённые такими отказами: их видно на странице статуса.
        self.refused_at: dict[int, str] = {}
        #: Куда сходило лечение бана: адреса POST по порядку.
        self.probed: list[str] = []
        self.mute = mute
        self.mute_all = mute_all
        #: Отвечает ли поисковая ручка особым 400 «выбранные индексеры недоступны».
        self.unavailable = unavailable
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
        if "/api/v1/indexerstatus?" in url:
            return _Reply(
                [
                    {
                        "indexerId": num,
                        "mostRecentFailure": failed,
                        "disabledTill": self.disabled_till.get(num, failed),
                    }
                    for num, failed in {**self.blocked, **self.refused_at}.items()
                ]
            )
        if "/api/v1/indexer/" in url:  # тело одного индексера - его же и понесёт проверка
            return _Reply({"id": int(url.split("/api/v1/indexer/")[1].split("?")[0])})
        if url.endswith("/api/v1/indexer?apikey=KEY"):
            return _Reply(
                [
                    {"id": 1, "name": "Knaben", "enable": True},
                    {"id": 2, "name": "RuTor", "enable": True},
                    {"id": 3, "name": "Nyaa.si", "enable": True},
                    {"id": 4, "name": "YTS", "enable": self.yts},
                ]
            )
        if self.unavailable:
            return _UnavailableReply([])
        num = int(url.rsplit("&indexerIds=", 1)[1])
        self.budget[str(num)] = timeout
        if held := self.stuck.get(num):
            time.sleep(held)
            raise requests.ConnectTimeout("залип дольше круга")
        pause = self.delay.get(num, 0.0)
        if pause > timeout:
            time.sleep(timeout)
            raise requests.ConnectTimeout("молчит")
        if pause:
            time.sleep(pause)
        if num in self.empty:
            return _Reply([])
        if num in self.refuses:  # источник не ответил, а наверх поехало «нашлось ноль»
            self.refused_at[num] = _ago(0)
            return _Reply([])
        if self.mute_all or num == self.mute:
            raise requests.ConnectTimeout("молчит")
        if num in self.hold and not self.gate.wait(timeout):
            raise requests.ConnectTimeout("молчит")
        return _Reply(self._rows(num))

    def post(self, url: str, json: object = None, timeout: float = 0.0) -> _Reply:
        """Проверка индексера - единственная ручка, которой снимается бан (TC-272)."""
        self.probed.append(url)
        return _Reply({})

    def _rows(self, num: int) -> list[dict[str, object]]:
        """Выдача одного индексера: при ``rows == 1`` - ровно одна строка (как было),
        иначе несколько строк с разными хэшами, чтобы склейка их не склеила."""
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


def _swarm(slack: float | None = None, budget_of: Any = None, **kwargs: Any) -> Prowlarr:
    """Клиент с подставным кругом индексеров; сроки круга задаются конструктором."""
    dependencies: dict[str, Any] = {}
    if slack is not None:
        dependencies["slack"] = slack
    if budget_of is not None:
        dependencies["budget_of"] = budget_of
    client = Prowlarr("http://127.0.0.1:9696/", "KEY", heal=_here, **dependencies)
    client._api.session = _Swarm(**kwargs)
    return client


def _swarm_of(client: Prowlarr) -> _Swarm:
    session = client._api.session
    assert isinstance(session, _Swarm)
    return session


def _asked(client: Prowlarr) -> list[str]:
    """Кого спросили персональным запросом - по номерам, в порядке круга.

    🔴 TC-686. Потоки круга пишут адреса в ``urls`` в том порядке, в каком их пустил
    планировщик, поэтому сырой список под параллельным набором выходил то
    ``["1", "2", "3"]``, то ``["2", "1", "3"]`` - и тест краснел на чужой правке.
    Предмет проверки - КТО спрошен, а не кто из потоков записался первым, поэтому
    номера сортируем. Что список к моменту чтения уже полон, гарантирует сам круг:
    ответов он ждёт событием ``ask.done``, а не паузой.
    """
    asked = (url.rsplit("=", 1)[1] for url in _swarm_of(client).urls if "&indexerIds=" in url)
    return sorted(asked, key=int)


def _here(work: Callable[[], None]) -> None:
    """Лечение бана в стороне, но в этом же круге: зеркалу нужен ответ, а не планировщик.

    Боевой путь уводит стук в демон-поток, и ждать его тест мог только настоящими
    часами - до двух секунд сна с ответом «пока ничего», который на нагруженной машине
    приходил не тот.
    """
    work()


def _probes(client: Prowlarr) -> list[str]:
    """Куда сходило лечение бана (TC-272)."""
    return _swarm_of(client).probed


def test_search_asks_every_indexer_apart() -> None:
    """Врозь - значит по запросу на индексер, и выключенный не спрашиваем вовсе."""
    client = _swarm()
    results = client.search("матрица")
    assert _asked(client) == ["1", "2", "3"]
    assert [r.title for r in results] == ["picture.1", "picture.2", "picture.3"]
    assert client.silent == ()


def test_source_ceiling_does_not_follow_requested_limit() -> None:
    """Полная страница источника остаётся потолком при большем клиентском лимите."""
    client = _swarm(rows=100)
    client.search("матрица", limit=200)
    assert client.capped == ("Knaben", "RuTor")


def test_one_silent_source_does_not_hide_another_sources_ceiling() -> None:
    """Молчание одного источника видно отдельно, потолок другого не пропадает."""
    client = _swarm(rows=100, mute=2)
    client.search("матрица", limit=200)
    assert client.silent == ("RuTor",)
    assert client.capped == ("Knaben",)


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
    assert max(_swarm_of(client).waited) < client.timeout


@pytest.mark.machine
def test_slow_extra_indexer_does_not_hold_the_ready_catalog() -> None:
    """A non-quorum tail may keep working, but the ready catalog returns immediately."""
    client = _swarm(hold={3}, rows=2)
    began = time.monotonic()
    try:
        results = client.search("Naruto [TV]")
        elapsed = time.monotonic() - began
    finally:
        _swarm_of(client).gate.set()

    assert len(results) == 4
    assert elapsed < 0.5
    # 🔴 TC-703. Ручка публичная: кто ещё в пути - признак неполноты выдачи, и о нём
    # спрашивают те, кто говорит человеку про каталог.
    assert client.waiting() == ("Nyaa.si",)


@pytest.mark.machine
def test_trace_carries_per_indexer_milliseconds(journal: Path) -> None:
    """Событие круга несёт время КАЖДОГО индексера - и ответившего, и молчуна.

    Замер наш, на месте вызова: elapsedTime истории Prowlarr врёт про провалившиеся
    и повторные попытки, и хвост круга (кто и сколько держал) без своего секундомера
    из следа не разобрать (TC-230).
    """
    client = _swarm(mute=2)
    client.search("матрица")
    shutdown()
    (row,) = [r for r in records() if r.get("event") == "indexers"]
    took = row["ms"]
    assert set(took) == {"Knaben", "RuTor", "Nyaa.si"}
    assert all(isinstance(ms, int) and ms >= 0 for ms in took.values())


def test_all_indexers_silent_is_infra_not_empty_result() -> None:
    """Молчат все до одного - это отказ инфраструктуры, а не «ничего не нашлось»."""
    with pytest.raises(InfraError, match="does not answer"):
        _swarm(mute_all=True).search("матрица")


def test_stuck_first_circle_names_the_silent_ones() -> None:
    """🔴 TC-513. Залипший дольше круга к этой секунде не ответил ничем - ни строкой, ни
    отказом, - и причина отказа инфры складывается из одних имён молчунов. Зритель обязан
    получить её словами: пустая строка не говорит ему, что делать дальше.

    Круг отпущен на 0.04 с при залипании на 0.4 с: пересечься эти сроки не могут, а сам
    запрос кончается отказом уже после круга - ровно как у живого молчуна.
    """
    client = _swarm(slack=0.02, budget_of=lambda _name: 0.02, stuck={1: 0.4, 2: 0.4, 3: 0.4})
    with pytest.raises(InfraError) as caught:
        client.search("матрица")
    assert str(caught.value) == "индексеры не отвечают: Knaben, RuTor"


def test_prowlarr_400_names_unavailable_indexers_not_prowlarr() -> None:
    """Особый 400 означает, что Prowlarr жив, а отказали выбранные индексеры."""
    client = _swarm(unavailable=True)
    with pytest.raises(InfraError) as caught:
        client.search("матрица")
    message = str(caught.value)
    assert message == "индексеры не отвечают: Knaben, RuTor"
    assert "Prowlarr не отвечает" not in message


class _UnavailableCircle(IndexerCircle):
    """Круг по индексерам, который всегда кончается их недоступностью."""

    def run(
        self, pairs: Sequence[Indexer], query: str, limit: int, cap: float = 0.0
    ) -> tuple[list[list[RawResult]], InfraError | None]:
        self.lost.extend(("Knaben", "RuTor"))
        return [], _IndexersUnavailableError("каталог временно недоступен")


def test_unavailable_indexers_are_recognized_by_type_not_message() -> None:
    """Отказ выбранных индексеров остаётся узнаваемым при любом тексте для человека."""
    client = _swarm()
    client._circle = _UnavailableCircle(client._api)

    with pytest.raises(InfraError, match=r"^индексеры не отвечают: Knaben, RuTor$"):
        client.search("матрица")


def test_заблокированный_индексер_не_занимает_места_в_круге() -> None:
    """🔴 TC-259. Забаненного Prowlarr'ом спрашивать нельзя: вместо его выдачи придёт
    отказ ВСЕГО поиска («all selected indexers being unavailable»), неотличимый от смерти
    самого Prowlarr. Места в круге и личного бюджета он при этом стоит как живой - и в
    списке индексеров выглядит включённым. Такой в круг не идёт и молчуном не зовётся:
    молчун не ответил нам, а этого мы и не спрашивали.
    """
    client = _swarm(yts=True, blocked={4: _ago(300)})
    results = client.search("матрица")
    assert "4" not in _asked(client)  # YTS заблокирован - персонального запроса не получает
    assert client.banned == ("YTS",)
    assert client.silent == ()  # заблокированный - не молчун
    assert results  # находки остальных на месте: смерть звена урезает каталог, а не показ


def test_бан_снимается_проверкой_индексера() -> None:
    """🔴 TC-272. Ручки «снять бан» у Prowlarr нет (DELETE на статус отвечает 405), и сам
    он отпускает по своим часам, а не по здоровью источника: замер на стенде - канал
    пропадал на 12 с, каталог был урезан ещё 59.2 с ПОСЛЕ его возврата, а на хронике
    отсрочка дорастает до часа. Снимает бан только успешная проверка индексера - она
    ходит в источник по-настоящему, поэтому вернуть мёртвого в каталог ею нельзя.
    """
    client = _swarm(yts=True, blocked={4: _ago(300)})
    client.search("матрица")
    assert _probes(client) == ["http://127.0.0.1:9696/api/v1/indexer/test?apikey=KEY"]


def test_свежий_отказ_проверками_не_добиваем() -> None:
    """Источник, отказавший только что, не трогаем: лишний запрос к трекеру - это ровно
    та причина, по которой Prowlarr и раздаёт баны (Nyaa отвечает на них 504)."""
    client = _swarm(yts=True, blocked={4: _ago(1)})
    client.search("матрица")
    assert _probes(client) == []
    assert client.banned == ("YTS",)  # в круг он всё равно не идёт


def test_суточную_отсрочку_лечебным_стуком_не_продлеваем() -> None:
    """Мёртвому источнику Prowlarr назначает сутки и каждым POST начинает их заново."""
    client = _swarm(
        yts=True,
        blocked={4: _ago(300)},
        disabled_till={4: _ago(-24 * 60 * 60)},
    )
    client.search("матрица")
    assert _probes(client) == []
    assert client.banned == ("YTS",)


def test_бан_всех_индексеров_это_отказ_инфры_а_не_пустой_поиск() -> None:
    """Заблокированы все до одного - каталога нет, и сказать это надо словами: пустая
    выдача вместо честного отказа тут была бы молчаливой подменой."""
    banned = {num: _ago(300) for num in (1, 2, 3)}
    with pytest.raises(InfraError, match="every indexer"):
        _swarm(blocked=banned).search("матрица")


def test_пустой_поиск_при_бане_кворумного_называет_урезанный_каталог() -> None:
    """«Ничего не нашлось» - утверждение о каталоге, а бан кворумного забирает его
    половину (замер: 41% строк на Knaben, 56% на RuTor - разные половины). Сказать об
    этом обязаны, но ОТКАЗОМ инфры пустота тут не становится: остальные-то ответили.

    🔴 TC-510. Прежде здесь был :class:`InfraError`, и он обрывал поиск целиком: его не
    ловит сценарий добора, а вместе с ним пропадали и добор второй строкой, и уже
    собранный пул. Замер офлайн (10 запросов, молчит один Knaben, остальные живы):
    6 отказов с кодом 2, и у четырёх из них меню было готово - 17, 6, 15 и 43 раздачи.
    """
    client = _swarm(rows=0, blocked={1: _ago(300)})
    with pytest.raises(NotFoundError, match="the catalogue is cut down") as caught:
        client.search("матрица")
    assert "Prowlarr took Knaben out of reach" in str(caught.value)


def test_пустой_поиск_при_бане_некворумного_остаётся_пустым_но_названным() -> None:
    """У некворумного замерен НОЛЬ запросов, где он единственный источник, - пустоту его
    бан не отменяет. Но человек должен знать, что искали урезанным каталогом."""
    client = _swarm(rows=0, yts=True, blocked={4: _ago(300)})
    with pytest.raises(NotFoundError, match="the catalogue is cut down"):
        client.search("матрица")


def test_пустота_отказавшего_источника_не_выдаётся_за_честный_ноль() -> None:
    """🔴 TC-291. Окно ПЕРЕД баном: источник уже не отвечает, а Prowlarr ещё отдаёт 200 [].

    Замер на живом стенде: источник отвечает отказом соединения - первый запрос приходит
    как «HTTP 200, строк 0», и только со второго начинается 400 «выбранные индексеры
    недоступны» (это уже TC-259). Одного запроса хватает, чтобы соврать про весь каталог:
    живьём на лежащем звене человеку сказали «ничего не нашлось».

    Улика при этом есть уже в первый миг - Prowlarr тогда же ставит себе отметку отказа.

    🔴 TC-510. Отказом инфры (кодом 2) пустота тут больше не становится - остальные
    источники ответили, и поиск обязан жить дальше. Подмена, от которой сторожит этот
    тест, осталась прежней: голое «ничего не нашлось» на лежащем звене - враньё.
    """
    client = _swarm(rows=0, refuses={1})  # Knaben, кворумный
    with pytest.raises(NotFoundError, match="a refusal at Knaben") as caught:
        client.search("матрица")
    assert "the catalogue is cut down" in str(caught.value), "пустота названа урезанной"


def test_отказ_некворумного_пустоту_не_отменяет_но_называется() -> None:
    """У некворумного замерен НОЛЬ запросов, где он единственный источник: пустота
    остаётся пустотой. Но искали урезанным каталогом, и человек должен это услышать."""
    client = _swarm(rows=0, yts=True, refuses={4})
    cut_at_yts = "the catalogue is cut down right now - a refusal at YTS"
    with pytest.raises(NotFoundError, match=cut_at_yts):
        client.search("матрица")


def test_честный_ноль_остаётся_честным() -> None:
    """🔴 Ограждение к TC-291: «ничего не нашлось» СУЩЕСТВУЕТ. Все ответили, все отдали
    ноль, отметок об отказах нет - это честная пустая полка, и подменять её отказом
    инфры значит врать во вторую сторону."""
    with pytest.raises(NotFoundError, match=r"^nothing was found for “матрица”$"):
        _swarm(rows=0).search("матрица")


def test_молчание_кворумного_названо_в_урезанном_каталоге() -> None:
    """🔴 TC-510. Молчание - третий способ выпасть из каталога, наравне с баном и с
    отказом за ``200 []``. Отметки Prowlarr при нём может не быть вовсе (бюджет круга
    короче его собственного терпения), и без этой строки пустота выглядела бы честной
    пустой полкой - при том, что 41% каталога мы просто не дождались."""
    client = _swarm(rows=0, mute=1)  # Knaben, кворумный, молчит
    cut_at_knaben = "the catalogue is cut down right now - Knaben keeps silent"
    with pytest.raises(NotFoundError, match=cut_at_knaben):
        client.search("матрица")


def test_молчание_круга_не_отменяет_поиск_в_котором_нам_уже_отвечали() -> None:
    """🔴 TC-510. Пустой круг - это не «молчит инфраструктура», если в этом же поиске нам
    уже отвечали. Кругов у поиска несколько: добор второй строкой, фолбэк по анимешным,
    переспрос забытой раскладки, - и каждый следующий идёт в остаток цели (TC-228),
    то есть в секунду-полторы. Молчание такого огрызка объявляло весь поиск отказом
    инфры, а отказ инфры не ловит сценарий добора: вместе с добором пропадал и уже
    собранный пул. Замер офлайн: так пропадало готовое меню у 4 запросов из 10.

    Отказ остаётся там, где он правдив: не ответил никто
    (:func:`test_all_indexers_silent_is_infra_not_empty_result`).
    """
    client = _swarm(rows=2)
    assert client.search("матрица"), "первый круг: нам ответили"
    _swarm_of(client).mute_all = True
    with pytest.raises(NotFoundError) as caught:
        client.search("матрица 2")
    assert "keeps silent" in str(caught.value), "молчуны названы, каталог урезан"


def test_non_anime_query_skips_nyaa_when_pool_is_rich() -> None:
    """🔴 TC-229: явно не-аниме запрос на полном пуле Nyaa не тревожит - тот молчит на
    79% запросов, и лишняя параллель по нему грозит 504-баном Prowlarr на часы."""
    client = _swarm(rows=2)  # Knaben и RuTor дают по две - пул не тощий
    results = client.search("матрица")
    assert _asked(client) == ["1", "2"]  # Nyaa (id 3) не спрошен вовсе
    assert client.silent == ()  # неспрошенный - не молчун
    assert len(results) == 4


def test_anime_query_calls_nyaa_in_the_main_circle() -> None:
    """Похожий на аниме запрос зовёт Nyaa сразу, а не фолбэком: пул тут и без него полный,
    так что фолбэк бы не сработал - значит Nyaa именно в основном круге."""
    client = _swarm(rows=2)
    results = client.search("Naruto [TV]")
    # Nyaa - не опорный, и круг вправе уйти до его ответа: хвост ждём СОБЫТИЕМ (долив
    # дожидается флаг потока), а не порядком, в котором успели потоки (TC-686).
    results += client.late(wait=SHORT_TIMEOUT)
    assert _asked(client) == ["1", "2", "3"]
    assert len(results) == 6


@pytest.mark.machine
def test_thin_pool_falls_back_to_nyaa(journal: Path) -> None:
    """Не-аниме запрос, но пул без анимешных вышел тощим - фолбэком зовём и Nyaa.
    В след это событие пишется флагом ``fallback`` (TC-229)."""
    client = _swarm()  # rows=1: Knaben + RuTor = две раздачи, ниже порога
    results = client.search("матрица")
    shutdown()
    assert _asked(client) == ["1", "2", "3"]  # 1 и 2 в основном круге, 3 добран фолбэком
    assert [r.title for r in results] == ["picture.1", "picture.2", "picture.3"]
    (row,) = [r for r in records() if r.get("event") == "indexers"]
    assert row["fallback"] is True


def test_yts_asked_in_its_own_short_budget() -> None:
    """🔴 TC-213: у YTS бюджет свой и короткий, у остальных - общий.

    Терять на нём нечего: замер TC-141 дал +2.1% к пулу и ноль запросов, где он
    единственный источник играбельного HD. А платили мы за него полным бюджетом:
    его выдачу рвёт канал на объёме тела, и молчание выбирало все 20 с (замер на
    стенде: «barbie» - 20.02 с). Честный ответ у него - 0.5-0.9 с.
    """
    client = _swarm(yts=True, rows=2)
    client.search("barbie 2023")  # латиница с годом - не аниме, Nyaa вне круга
    assert _swarm_of(client).budget == {"1": LATE_TIMEOUT, "2": 3.0, "4": SHORT_TIMEOUT}


def test_silent_yts_costs_only_its_short_budget() -> None:
    """Молчащий YTS не держит круг общим бюджетом: и отметка называет его цену честно."""
    client = _swarm(yts=True, rows=2, mute=4)
    results = client.search("barbie 2023")
    assert [r.indexer for r in results] == ["idx.1", "idx.1", "idx.2", "idx.2"]
    assert client.silent == ("YTS",)
    assert _swarm_of(client).budget["4"] == SHORT_TIMEOUT


def test_show_survives_when_nyaa_is_silent_in_fallback() -> None:
    """Деградация: Nyaa недоступен на фолбэке - его имя уходит в молчуны, находки
    остальных доезжают, показ не ломается."""
    client = _swarm(mute=3)  # тощий пул -> фолбэк зовёт Nyaa, а тот молчит
    results = client.search("матрица")
    assert [r.title for r in results] == ["picture.1", "picture.2"]
    assert client.silent == ("Nyaa.si",)


def test_круг_уходит_по_кворуму_не_дожидаясь_остальных() -> None:
    """🔴 TC-118: круг возвращается, когда ответили опорные (Knaben + RuTor), а не когда
    отговорили все четверо. Опоздавший (Nyaa) в этот момент ещё держит соединение - и
    раньше держал бы вместе с ним всё меню, до своего полного бюджета в 20 с."""
    client = _swarm(rows=2, hold={3})  # Nyaa не отпустят до отмашки
    try:
        results = client.search("Naruto [TV]")  # аниме-запрос: Nyaa в основном круге
        assert len(results) == 4  # Knaben и RuTor по две раздачи, Nyaa не дождались
        assert client.silent == ()  # опоздавший - не молчун: он ещё в пути
    finally:
        # Отмашка и долив: поток опоздавшего дожидается тут, а не в чужой пробе.
        _swarm_of(client).gate.set()
        client.late(wait=5.0)


def test_опоздавший_доливается_после_круга_а_не_теряется() -> None:
    """Выдача опоздавшего не выбрасывается: она забирается :meth:`Prowlarr.late` уже
    после того, как список показан. Пока индексер в пути, долив пуст - ждать его на
    пути до меню и значило бы не уходить по кворуму."""
    client = _swarm(rows=2, hold={3})
    client.search("Naruto [TV]")
    assert client.late() == []  # ещё в пути - долив ничего не обещает
    _swarm_of(client).gate.set()
    late = client.late(wait=5.0)
    assert len(late) == 2  # доехали ровно раздачи Nyaa
    assert client.late() == []  # долив разовый: второй раз брать нечего


def test_поздний_ответ_живёт_дольше_бюджета_круга() -> None:
    """TC-454: бюджет круга выпускает меню, но не обрывает честный поздний ответ.

    Knaben здесь отвечает после своего искусственно короткого бюджета. Круг обязан
    оставить запрос в доливе, а долив - получить строки из того же запроса.
    """
    client = _swarm(
        slack=0.0,
        budget_of=lambda name: 0.02 if name == "Knaben" else indexer_budget(name),
        rows=2,
        delay={1: 0.06},
    )

    results = client.search("матрица")

    assert [r.indexer for r in results] == ["idx.2", "idx.2", "idx.3", "idx.3"]
    assert client.silent == ("Knaben",), "на пути к меню молчание названо честно"
    late = client.late(wait=0.2)
    assert [r.indexer for r in late] == ["idx.1", "idx.1"]
    assert _swarm_of(client).budget["1"] > 0.06


def test_пустой_пул_дожидается_опоздавшего() -> None:
    """🔴 TC-318. Пул пуст, а опоздавший ещё в пути - тогда его дожидаются: сказать
    «ничего не нашлось» про каталог, у которого не спросили последнего, нельзя.

    Честный ноль ответивших идёт тут наравне с молчанием: строк не приехало ни одной, и
    выбор у человека тот же - пусто или картина.
    """
    client = _swarm(rows=2, empty={1, 2}, hold={3})
    threading.Timer(0.2, _swarm_of(client).gate.set).start()
    try:
        results = client.search("Naruto [TV]")
    finally:
        _swarm_of(client).gate.set()
    assert [r.title for r in results] == ["picture.3.0", "picture.3.1"]


def test_ожидание_опоздавшего_не_длиннее_остатка_цели() -> None:
    """Ждать на пустом пуле - решение про остаток цели (:meth:`Prowlarr.spare`), а не про
    бюджет опоздавшего: цели не осталось - ждать нечем, и пустой ответ приходит сразу."""
    client = _swarm(rows=2, empty={1, 2}, hold={3})
    client._began = time.monotonic() - 30.0  # цель съедена целиком
    assert client.spare() == 0.0
    began = time.monotonic()
    try:
        with pytest.raises(NotFoundError, match="nothing was found"):
            client.search("Naruto [TV]")
    finally:
        _swarm_of(client).gate.set()
    assert time.monotonic() - began < 1.0


def test_rutor_дожидаемся_но_он_не_держит_каталог() -> None:
    """TC-487: живому RuTor даём коротко доехать, но его смерть не убивает поиск."""
    client = _swarm(rows=2, hold={2})
    threading.Timer(0.2, _swarm_of(client).gate.set).start()
    results = client.search("Naruto [TV]")
    assert len(results) == 6  # все трое: круг дождался кворумного
    assert client.late() == []  # опоздавших нет вовсе


def test_мёртвый_rutor_деградирует_за_три_секунды() -> None:
    """Остальные результаты доезжают, RuTor назван молчуном и не стоит общей цели."""
    client = _swarm(rows=2, mute=2)
    results = client.search("матрица")
    assert results
    assert "idx.2" not in {row.indexer for row in results}
    assert client.silent == ("RuTor",)
    assert indexer_budget("RuTor") == 3.0


def test_круг_без_кворумных_ждёт_всех() -> None:
    """Фолбэк по анимешным (TC-229) идёт без кворумных вовсе - ждать в нём некого,
    поэтому такой круг дожидается всех спрошенных. Иначе он возвращался бы пустым."""
    client = _swarm(hold={3})  # rows=1: пул тощий, фолбэк зовёт Nyaa
    threading.Timer(0.2, _swarm_of(client).gate.set).start()
    results = client.search("матрица")
    assert [r.title for r in results] == ["picture.1", "picture.2", "picture.3"]


def test_второй_круг_идёт_в_остаток_цели() -> None:
    """🔴 TC-228. Первый круг - это и есть поиск, у него личные бюджеты. А каждый
    следующий (добор вторым языком, сезонная строка, чтение раскладки) платит из остатка
    цели: раньше он платил хвост первого круга ПЛЮС свой полный, и на хвосте Knaben это
    давало 30 с при цели в 10."""
    client = _swarm(rows=2)
    client.search("Naruto [TV]")
    client._began = time.monotonic() - 8.0  # изобразим поиск, съевший 8 секунд цели
    assert 1.5 < client.circle_cap() <= 2.0, "второму кругу достаётся остаток цели"


def test_огрызок_бюджета_доводится_до_секунды() -> None:
    """Цель съедена целиком, а спрашивать всё-таки идём (пустая выдача, чтение забытой
    раскладки) - тогда круг спрашивается хотя бы на секунду. Круг с нулевым бюджетом это
    не экономия, а гарантированный молчун ценой в лишний запрос к трекеру."""
    client = _swarm(rows=2)
    client.search("Naruto [TV]")
    client._began = time.monotonic() - 30.0  # цели не осталось вовсе
    assert client.spare() == 0.0
    assert client.circle_cap() == 1.0


def test_пол_второго_круга_поднимается_добором_до_цели() -> None:
    """🔴 TC-386. Добор по второму имени картины поднимает пол бюджета круга до целой
    цели: медленный, но живой индексер (на живом стенде Knaben отвечал 7.0 с вместо
    0.5) в секундный остаток не укладывается, и добор проходил формально, не привезя
    ничего, - картина пропадала из каталога, как при отмене. По умолчанию пол прежний:
    одна секунда (:data:`~torrcast.domain.goal_spare.CIRCLE_SHARE`)."""
    client = _swarm(rows=2)
    assert client.cap_floor == 1.0, "пол по умолчанию - доля круга, как прежде"
    client.search("Naruto [TV]")
    client._began = time.monotonic() - 30.0  # цели не осталось вовсе
    client.cap_floor = 10.0  # так делает добор по второму имени
    assert client.circle_cap() == 10.0


@pytest.mark.machine
def test_след_отличает_опоздавшего_от_молчуна(journal: Path) -> None:
    """Опоздавший и молчун - разные причины хвоста, и в следе они врозь: иначе `cast log`
    объяснял бы задержку кругом, которого не было."""
    client = _swarm(rows=2, hold={3})
    client.search("Naruto [TV]")
    _swarm_of(client).gate.set()  # отмашка опоздавшему: его поток кончается тут
    client.late(wait=5.0)
    shutdown()
    (row,) = [r for r in records() if r.get("event") == "indexers"]
    assert row["late"] == ["Nyaa.si"]
    assert row["silent"] == []
    assert "late Nyaa.si" in digest(records())
