"""Проверяет полку начала ленты: замер другого процесса доезжает до показа без ffprobe."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from torrcast.adapters.pack_memory import _ORIGIN
from torrcast.adapters.stream_pack._origin_shelf import _origin_cache
from torrcast.adapters.stream_pack.pack_origin import pack_origin
from torrcast.domain.hls_settings import AUDIO_PRIMING

URL = "http://торрент/поток?link=0123456789abcdef&index=0"


@pytest.fixture(autouse=True)
def _own_memory() -> Iterator[None]:
    """Память процесса пуста у каждой пробы: полка - единственное, что переживает процесс."""
    _ORIGIN.clear()
    yield
    _ORIGIN.clear()


class Probe:
    """Подделка ffprobe: отвечает названным провалом и считает, сколько раз её звали."""

    def __init__(self, slack: float | None) -> None:
        self.slack, self.calls = slack, 0

    def __call__(self, url: str, timeout: float) -> float | None:
        self.calls += 1
        return self.slack


def test_the_show_takes_the_origin_measured_by_another_process_from_the_shelf() -> None:
    """🔴 Прогрев карточки и прошлый показ - другие процессы: их замер не должен меряться снова."""
    warm = Probe(0.08)
    first = pack_origin(URL, slack_of=warm)
    _ORIGIN.clear()  # показ - свежий процесс со своей пустой памятью
    show = Probe(0.5)
    assert pack_origin(URL, slack_of=show) == first
    assert show.calls == 0, "показ позвал ffprobe, хотя начало ленты лежало на полке"


@pytest.mark.parametrize(
    "body",
    ["{не json", json.dumps({"source": "http://чужой/поток", "slack": 0.08}),
     json.dumps({"source": URL, "slack": -1.0}), json.dumps({"source": URL})],
    ids=["битая", "чужая", "ниже нуля", "без замера"],
)  # fmt: skip
def test_a_broken_or_foreign_record_is_a_miss_not_a_wrong_origin(body: str) -> None:
    """Неверное начало ленты стоит мёртвого показа, поэтому сомнительная запись - промах."""
    cache = _origin_cache(URL)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(body, "utf-8")
    probe = Probe(0.2)
    assert pack_origin(URL, slack_of=probe) == pytest.approx(0.2 + AUDIO_PRIMING, abs=0.001)
    assert probe.calls == 1


def test_a_file_that_was_not_read_is_not_put_on_the_shelf() -> None:
    """Не прочли - это не замер: следующий процесс обязан попробовать снова, а не взять набивку."""
    pack_origin(URL, slack_of=Probe(None))
    _ORIGIN.clear()
    probe = Probe(0.08)
    pack_origin(URL, slack_of=probe)
    assert probe.calls == 1
