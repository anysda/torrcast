"""Ранний отказ на мёртвом рое (TC-60).

Живой репорт: «cast cars» -> одна картина -> «дорожки... 40.0 с» -> «релиз не годится
(ffprobe не дождался потока)». Раздача с мёртвым роем метаданные отдаёт (они уже в
TorrServer), а содержимого не отдаёт вовсе, и весь :data:`PROBE_BUDGET` сгорал на ОДНОМ
молчащем релизе — при том что запасной уже грелся параллельно. Правило TC-39 («молчание
роя не жжёт попытку») тут не спасало: кандидат был один.

Признак жизни (:func:`swarm_pulse`) отличает молчащий рой от честно долгого заголовка
(«Моана 2» едет 17 с) и даёт оборвать ffprobe рано, не жгя весь бюджет.
"""

from __future__ import annotations

import subprocess
import time
from typing import Any, cast

import pytest

from torrcast import InfraError, cli
from torrcast import stream as stream_mod
from torrcast.parse import Release
from torrcast.stream import Media, swarm_pulse

from tests.test_cli import _FakeTorrServer, _resolve, rel


def test_run_ffprobe_returns_the_moment_the_probe_exits() -> None:
    """Живой релиз не ждёт бюджета: как только ffprobe вышел, отдаём его вывод."""
    began = time.monotonic()
    out = stream_mod._run_ffprobe(["printf", "hello"], timeout=40.0, alive=lambda: True)
    assert out == "hello"
    assert time.monotonic() - began < 2.0


def test_run_ffprobe_bails_at_once_on_a_swarm_declared_dead() -> None:
    """Рой признан мёртвым — обрываем ffprobe сразу, а не досиживаем весь timeout."""
    began = time.monotonic()
    with pytest.raises(InfraError, match="рой молчит"):
        stream_mod._run_ffprobe(["sleep", "40"], timeout=40.0, alive=lambda: False)
    assert time.monotonic() - began < 3.0


def test_run_ffprobe_keeps_the_full_budget_while_the_stream_is_alive() -> None:
    """Пока поток жив, бюджет тратится полностью и таймаут остаётся прежним."""
    began = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        stream_mod._run_ffprobe(["sleep", "40"], timeout=0.5, alive=lambda: True)
    assert 0.4 <= time.monotonic() - began < 4.0


class _Body:
    def __init__(self, chunk: bytes) -> None:
        self._chunk = chunk

    def __enter__(self) -> _Body:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def read(self, _size: int) -> bytes:
        return self._chunk


def test_swarm_pulse_calls_a_byteless_stream_dead_only_after_the_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ни байта за отсрочку — рой мёртв; но пока отсрочка идёт, ждём: рой ещё может ожить."""
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Body(b""))
    alive = swarm_pulse("http://ts/x/0", grace=0.2)
    assert alive()  # отсрочка не вышла — терпим
    time.sleep(0.3)
    assert not alive()  # байт нет и отсрочка вышла — рой молчит


def test_swarm_pulse_stays_alive_once_a_byte_arrives(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пришёл байт — раздача жива и читается: обрывать её нельзя даже после отсрочки."""
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Body(b"\x00" * 4096))
    alive = swarm_pulse("http://ts/x/0", grace=0.05)
    time.sleep(0.2)  # отсрочка давно вышла
    assert alive()  # но байт был — раздача честно читается


def test_a_silent_stream_is_dropped_before_the_full_probe_budget(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Верх молчит потоком (метаданные есть, содержимого нет) — отказ приходит за отсрочку,
    а не за все сорок секунд PROBE_BUDGET, и показ уходит к живому запасному.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    monkeypatch.setattr(Release, "magnet", property(lambda self: f"magnet-{self.raw_name}"))
    monkeypatch.setattr(cli, "SWARM_GRACE", 0.3)

    def read(url: str, timeout: float = 90.0, alive: Any = None) -> Media:
        if "hash-magnet-r0/" in url:  # верх: рой молчит потоком
            end = time.monotonic() + timeout
            while alive is None or alive():
                if time.monotonic() >= end:
                    raise InfraError("ffprobe не дождался потока")
                time.sleep(0.02)
            raise InfraError("рой молчит - за отсрочку не пришло ни байта потока")
        return Media(3600.0, (), "h264")

    monkeypatch.setattr(cli, "probe", read)

    began = time.monotonic()
    prep = _resolve(cli._Bench(cast(Any, _FakeTorrServer())), ranked)
    elapsed = time.monotonic() - began

    printed = capsys.readouterr().out
    assert prep.number == 2, "молчащий поток не останавливает показ"
    assert "релиз 1 не годится (рой молчит" in printed and "беру 2" in printed
    assert elapsed < cli.PROBE_BUDGET, "не сожгли весь бюджет на молчащем релизе"
