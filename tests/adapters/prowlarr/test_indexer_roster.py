"""Проверяет список индексеров и работу с теми, кого Prowlarr увёл в недоступные."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from torrcast.adapters.prowlarr.indexer_roster import IndexerRoster
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.domain.infra_error import InfraError


def _ago(seconds: float) -> str:
    """Отметка глазами Prowlarr: UTC с ``Z``. Отрицательные секунды - будущее."""
    return (datetime.now(UTC) - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Http:
    """Подставные страницы Prowlarr: список индексеров и страница недоступных."""

    def __init__(
        self,
        indexers: list[dict[str, Any]] | None = None,
        blocked: dict[int, str] | None = None,
        disabled_till: dict[int, str] | None = None,
        dead: bool = False,
    ) -> None:
        self.indexers = indexers if indexers is not None else _LIST
        self.blocked = blocked or {}
        self.disabled_till = disabled_till or {}
        self.dead = dead
        self.asked: list[str] = []
        self.probed: list[tuple[str, str]] = []

    def new_session(self) -> Any:
        return "сессия"

    def get_json(self, session: Any, url: str, timeout: float, base_url: str) -> Any:
        self.asked.append(url)
        if self.dead:
            raise InfraError("Prowlarr не отвечает")
        if "/api/v1/indexerstatus" in url:
            return [
                {
                    "indexerId": num,
                    "mostRecentFailure": failed,
                    "disabledTill": self.disabled_till.get(num, failed),
                }
                for num, failed in self.blocked.items()
            ]
        return self.indexers

    def post(self, session: Any, url: str, body: Any, timeout: float) -> None:
        return None

    def probe(
        self,
        session: Any,
        indexer_url: str,
        test_url: str,
        list_timeout: float,
        test_timeout: float,
        base_url: str,
    ) -> None:
        self.probed.append((indexer_url, test_url))


_LIST: list[dict[str, Any]] = [
    {"id": 1, "name": "Knaben", "enable": True},
    {"id": 2, "name": "RuTor", "enable": True},
    {"id": 4, "name": "YTS", "enable": False},
]


def _here(work: Callable[[], None]) -> None:
    """Стук в стороне, но в этом же круге: зеркалу нужен ответ, а не планировщик.

    Боевой путь уводит стук в демон-поток, и ждать его тест мог только настоящими
    часами: до двух секунд сна, ответ - «пока ничего», и на нагруженной машине он
    приходил не тот. Ждать тут нечего вовсе - лечение либо постучалось, либо нет.
    """
    work()


def _roster(**kwargs: Any) -> tuple[IndexerRoster, _Http]:
    http = _Http(**kwargs)
    return IndexerRoster(ProwlarrApi("http://p", "KEY", http=http), spawn=_here), http


def test_выключенные_индексеры_в_список_не_попадают() -> None:
    roster, _http = _roster()
    assert roster.known() == ((1, "Knaben"), (2, "RuTor"))


def test_список_спрашивается_один_раз_на_поиск() -> None:
    """Он локальный, но и лишний поход по нему стоит места на критическом пути."""
    roster, http = _roster()
    roster.known()
    roster.known()
    assert len([url for url in http.asked if url.endswith("indexer?apikey=KEY")]) == 1


def test_мёртвый_prowlarr_даёт_пустой_список_а_не_отказ() -> None:
    """Пусто - значит спрашивать придётся прежним общим запросом, вслепую."""
    roster, _http = _roster(dead=True)
    assert roster.known() == ()


def test_заблокированный_не_занимает_места_в_круге() -> None:
    """🔴 TC-259. Забаненный так и стоит ``enable: true``, а спросить его нельзя:
    вместо выдачи придёт отказ всего поиска."""
    roster, _http = _roster(blocked={1: _ago(300)})
    usable, banned = roster.usable(roster.known())
    assert usable == ((2, "RuTor"),)
    assert banned == ("Knaben",)


def test_бан_всех_индексеров_это_отказ_инфры_а_не_пустой_поиск() -> None:
    """Заблокированы все до одного - каталога нет, и сказать это надо словами."""
    roster, _http = _roster(blocked={1: _ago(300), 2: _ago(300)})
    with pytest.raises(InfraError, match="все индексеры"):
        roster.usable(roster.known())


def test_отдохнувший_бан_лечим_проверкой_индексера() -> None:
    """🔴 TC-272. Ручки «снять бан» у Prowlarr нет: отсрочку гасит только успешная
    проверка, а она ходит в источник по-настоящему."""
    roster, http = _roster(blocked={1: _ago(300)})
    roster.usable(roster.known())
    assert http.probed == [
        ("http://p/api/v1/indexer/1?apikey=KEY", "http://p/api/v1/indexer/test?apikey=KEY")
    ]


def test_свежий_отказ_проверками_не_добиваем() -> None:
    roster, http = _roster(blocked={1: _ago(1)})
    roster.usable(roster.known())
    assert http.probed == []


def test_отказ_этого_поиска_назван_а_чужой_нет() -> None:
    """🔴 TC-291. Отметку ставит сам отказ, поэтому спрашиваем её ПОСЛЕ круга."""
    roster, _http = _roster(blocked={1: _ago(0), 2: _ago(3600)})
    assert roster.refused(banned=(), since=time.time()) == ("Knaben",)


def test_уже_забаненных_в_отказавшие_не_записываем() -> None:
    """Их мы и не спрашивали, а отметку им мог обновить наш же лечебный стук."""
    roster, _http = _roster(blocked={1: _ago(0)})
    assert roster.refused(banned=("Knaben",), since=time.time()) == ()
