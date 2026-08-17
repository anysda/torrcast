"""Проверяет круг по индексерам: свой бюджет каждому, уход по опорным, долив."""

from __future__ import annotations

import time
from typing import Any

import pytest

from torrcast.adapters.prowlarr.indexer_circle import IndexerCircle
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.domain.infra_error import InfraError

_KNABEN = (1, "Knaben")
_RUTOR = (2, "RuTor")
_NYAA = (3, "Nyaa.si")


class _Http:
    """Подставной HTTP-клиент: отвечает по номеру индексера, умеет молчать и тянуть."""

    def __init__(
        self,
        rows: int = 1,
        mute: set[int] | None = None,
        delay: dict[int, float] | None = None,
        empty: set[int] | None = None,
    ) -> None:
        self.rows = rows
        self.mute = mute or set()
        self.delay = delay or {}
        self.empty = empty or set()
        #: С каким сроком спросили каждого: круг задаёт его отдельно от своего бюджета.
        self.budget: dict[int, float] = {}

    def new_session(self) -> Any:
        return "сессия"

    def get_json(self, session: Any, url: str, timeout: float, base_url: str) -> Any:
        num = int(url.rsplit("&indexerIds=", 1)[1])
        self.budget[num] = timeout
        pause = self.delay.get(num, 0.0)
        if pause > timeout:
            time.sleep(timeout)
            raise InfraError("молчит")
        if pause:
            time.sleep(pause)
        if num in self.mute:
            raise InfraError("молчит")
        if num in self.empty:
            return []
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

    def post(self, session: Any, url: str, body: Any, timeout: float) -> None:
        return None

    def probe(self, *args: Any) -> None:
        return None


def _circle(slack: float = 0.05, **kwargs: Any) -> tuple[IndexerCircle, _Http]:
    http = _Http(**kwargs)
    api = ProwlarrApi("http://p", "KEY", http=http)
    return IndexerCircle(api, slack=slack, budget_of=lambda name: 0.5), http


def test_круг_спрашивает_каждого_и_считает_расклад() -> None:
    circle, _http = _circle(rows=2)
    got, error = circle.run([_KNABEN, _RUTOR], "матрица", 100)
    assert error is None
    assert [len(batch) for batch in got] == [2, 2]
    assert circle.counts == {"Knaben": 2, "RuTor": 2}
    assert set(circle.spent) == {"Knaben", "RuTor"}
    assert circle.answered == {"Knaben", "RuTor"}
    assert circle.lost == []


def test_честный_ноль_считается_ответом() -> None:
    """🔴 TC-510: каталог свой источник показал, и пустота такого поиска - «нет такого
    фильма», а не «нечем искать»."""
    circle, _http = _circle(empty={1})
    got, _error = circle.run([_KNABEN], "матрица", 100)
    assert got == [[]]
    assert circle.answered == {"Knaben"}
    assert circle.lost == []


def test_молчание_опорного_названо_а_находки_остальных_доезжают() -> None:
    circle, _http = _circle(rows=2, mute={2})
    got, error = circle.run([_KNABEN, _RUTOR], "матрица", 100)
    assert [len(batch) for batch in got] == [2]
    assert circle.lost == ["RuTor"]
    assert isinstance(error, InfraError)


@pytest.mark.machine
def test_круг_уходит_по_опорным_а_опоздавший_не_молчун() -> None:
    """🔴 TC-118. Некворумный круг не держал вовсе, поэтому раньше личного срока
    молчуном он не зовётся: его поток живёт дальше, а выдачу забирает долив."""
    circle, _http = _circle(rows=2, delay={3: 0.4})
    began = time.monotonic()
    got, _error = circle.run([_KNABEN, _NYAA], "Naruto [TV]", 100)
    elapsed = time.monotonic() - began
    assert [len(batch) for batch in got] == [2], "выдача опорного показана сразу"
    assert elapsed < 0.4, "опоздавшего круг не ждёт"
    assert circle.lost == []
    assert circle.waiting() == ("Nyaa.si",)


@pytest.mark.machine
def test_долив_забирает_опоздавшего_ровно_один_раз() -> None:
    circle, _http = _circle(rows=2, delay={3: 0.15})
    circle.run([_KNABEN, _NYAA], "Naruto [TV]", 100)
    late = circle.late(wait=2.0)
    assert [row.indexer for row in late] == ["idx.3", "idx.3"]
    assert circle.answered >= {"Knaben", "Nyaa.si"}, "опоздавший тоже ответил (TC-510)"
    assert circle.late() == [], "долив разовый: второй раз брать нечего"
    assert circle.waiting() == ()


@pytest.mark.machine
def test_долив_без_ожидания_ничего_не_обещает() -> None:
    """Ждать по умолчанию значило бы не уходить по опорным вовсе."""
    circle, http = _circle(rows=2, delay={3: 0.5})
    circle.run([_KNABEN, _NYAA], "Naruto [TV]", 100)
    assert circle.late() == []
    assert circle.waiting() == ("Nyaa.si",)
    del http


@pytest.mark.machine
def test_потолок_круга_режет_бюджет_но_не_срок_ответа() -> None:
    """TC-455: малый остаток цели ограничивает круг, но не срок HTTP-ответа."""
    circle, http = _circle(rows=2, delay={3: 0.04})
    got, error = circle.run([_NYAA], "Naruto [TV]", 100, cap=0.02)
    assert error is None
    assert len(got) == 1 and len(got[0]) == 2
    assert http.budget[3] > 0.04, "запрос живёт в личный срок индексера"


@pytest.mark.machine
def test_круг_без_опорных_дожидается_всех() -> None:
    """Фолбэк по анимешным идёт без опорных вовсе - ждать в нём некого, иначе он
    возвращался бы пустым."""
    circle, _http = _circle(rows=2, delay={3: 0.05})
    got, _error = circle.run([_NYAA], "матрица", 100)
    assert [len(batch) for batch in got] == [2]
    assert circle.waiting() == ()


def test_новый_расклад_не_помнит_прошлый_круг_но_помнит_ответивших() -> None:
    """Молчуны и счёт строк - про этот круг, а «было ли чем искать» - про весь поиск."""
    circle, _http = _circle(rows=2, mute={2})
    circle.run([_KNABEN, _RUTOR], "матрица", 100)
    assert circle.lost == ["RuTor"]
    circle.begin()
    assert circle.lost == [] and circle.counts == {} and circle.spent == {}
    assert circle.answered == {"Knaben"}
