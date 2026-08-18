"""Запас показа в кэше службы: `cast status` говорит о нём минутами, а не гигабайтами.

Число берётся из счётчика, который служба ведёт сама (`POST /cache`, `Filled`), и из
битрейта файла в записи состояния. Здесь служба подставная, но ответ её - настоящей
формы (снят с MatriX.142): ``Capacity``/``Filled`` и больше ничего нужного.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from tests.fakes import composition
from tests.fakes.show_unit import FakeShowUnit
from torrcast.adapters.filesystem.state import State
from torrcast.cli.main import main
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.server_down_error import ServerDownError
from torrcast.usecases.cache_reserve import _cache_reserve

KEY = "movie:моана-2:2024"
HASH = "a" * 40
MINUTES_120 = 7200.0


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))


class _FakeTorrServer:
    """Служба в объёме одного ответа на счётчик кэша; ``payload=None`` - она умерла."""

    payload: ClassVar[dict[str, Any] | None] = {"Capacity": 8 * 1024**3, "Filled": 0}

    def __init__(self, url: str, timeout: float = 3.0) -> None:
        self.url, self.timeout = url, timeout

    def cache(self, torrent_hash: str) -> dict[str, Any]:
        assert torrent_hash == HASH, "спросили не свою раздачу"
        if _FakeTorrServer.payload is None:
            raise ServerDownError("TorrServer не отвечает")
        return _FakeTorrServer.payload


def _server(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any] | None) -> None:
    _FakeTorrServer.payload = payload
    composition.use_engines(monkeypatch, _FakeTorrServer)


def _entry(**fields: Any) -> Entry:
    defaults: dict[str, Any] = {
        "title": "Моана 2",
        "magnet": "magnet:?xt=1",
        "dur": MINUTES_120,
        "pos": 600.0,
        "torrent": HASH,
        "vbps": 10.0,
    }
    return Entry(**{**defaults, **fields})


def test_reserve_is_minutes_of_this_release(monkeypatch: pytest.MonkeyPatch) -> None:
    """Полгигабайта при 10 Мбит/с - это 7 минут показа, а не «0.5 ГБ»."""
    _server(monkeypatch, {"Capacity": 8 * 1024**3, "Filled": 500_000_000})

    line = _cache_reserve(Config(), _entry())

    assert line == "в кэше службы запас ещё на 7 мин показа"


def test_reserve_depends_on_bitrate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тот же набитый кэш на тяжёлом релизе - заметно меньше минут: число не константа."""
    _server(monkeypatch, {"Capacity": 8 * 1024**3, "Filled": 500_000_000})

    heavy = _cache_reserve(Config(), _entry(vbps=40.0))

    assert heavy == "в кэше службы запас ещё на 2 мин показа"


def test_empty_cache_is_an_honest_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """Запаса нет - об этом говорится вслух, а не молчанием."""
    _server(monkeypatch, {"Capacity": 8 * 1024**3, "Filled": 0})

    assert _cache_reserve(Config(), _entry()) == "кэш службы пуст, запаса показа в нём нет"


def test_dead_service_degrades_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Служба умерла - честное «не знаю», а не исключение: показ от этого не ломается."""
    _server(monkeypatch, None)

    line = _cache_reserve(Config(), _entry())

    assert line == "запас в кэше службы неизвестен - служба раздач не отвечает"


def test_silent_service_degrades_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Служба ответила, но про кэш молчит (версия без счётчика) - то же «не знаю»."""
    _server(monkeypatch, {"Hash": HASH})

    line = _cache_reserve(Config(), _entry())

    assert line == "запас в кэше службы неизвестен - служба про него молчит"


def test_unknown_bitrate_does_not_invent_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Паспорт битрейта промолчал (в записи -1) - минуты не выдумываются."""
    _server(monkeypatch, {"Capacity": 8 * 1024**3, "Filled": 500_000_000})

    line = _cache_reserve(Config(), _entry(vbps=-1.0))

    assert line == "запас в кэше службы есть, в минуты не перевести - битрейт файла неизвестен"


def test_no_hash_no_question(monkeypatch: pytest.MonkeyPatch) -> None:
    """Хэша раздачи в записи нет - спрашивать нечего, и строки нет вовсе."""
    _server(monkeypatch, {"Capacity": 8 * 1024**3, "Filled": 500_000_000})

    assert _cache_reserve(Config(), _entry(torrent="")) == ""


def test_tiny_reserve_is_honest(monkeypatch: pytest.MonkeyPatch) -> None:
    """Меньше минуты запаса не округляется до «1 мин»."""
    _server(monkeypatch, {"Capacity": 8 * 1024**3, "Filled": 30_000_000})

    assert _cache_reserve(Config(), _entry()) == "в кэше службы запас меньше минуты показа"


def test_status_prints_the_reserve(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`cast status` во время показа говорит запас кэша рядом с позицией."""
    _server(monkeypatch, {"Capacity": 8 * 1024**3, "Filled": 500_000_000})
    state = State()
    state.put(KEY, _entry())
    state.save()
    show_unit.alive = True
    show_unit.playing = KEY

    assert main(["status"]) == 0

    out = capsys.readouterr().out
    assert "играю «Моана 2» - 0:10:00 / 2:00:00" in out
    assert "в кэше службы запас ещё на 7 мин показа" in out


def test_status_survives_dead_service(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Мёртвая служба сужает статус до «не знаю», сам статус работает."""
    _server(monkeypatch, None)
    state = State()
    state.put(KEY, _entry())
    state.save()
    show_unit.alive = True
    show_unit.playing = KEY

    assert main(["status"]) == 0

    out = capsys.readouterr().out
    assert "играю «Моана 2»" in out
    assert "запас в кэше службы неизвестен - служба раздач не отвечает" in out
