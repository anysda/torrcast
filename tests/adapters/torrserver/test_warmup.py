"""Проверяет результат фонового прогрева без настоящего потока."""

from tests.fakes.clock import FakeClock
from torrcast.adapters.torrserver.warmup import Warmup


def test_готовый_прогрев_возвращает_hash() -> None:
    warmup = Warmup(magnet="magnet", clock=FakeClock(), torrent_hash="hash")
    assert warmup.result() == "hash"
