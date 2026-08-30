"""Зеркало :mod:`torrcast.usecases.source_blame`: виноват ли ИСТОЧНИК в погасшем показе.

Занятие маленькое, но общее: спрашивают источник и показ, и оживление показа. Ровно ради
этого оно и вынесено отдельно - пока оба вопроса жили внутри показа, оживлению приходилось
брать их оттуда, и пара модулей замыкалась друг на друга.

Сторожится здесь то, что дороже всего стоило замеров на живой службе: один вопрос в момент
смерти застаёт перезапущенную службу уже здоровой и врёт, поэтому вопросов несколько; а
служба, которой мы сами вернули раздачу магнитом, виновата даже когда отвечает «всё
хорошо». Ниже - и то, и другое, и цена вопроса: молчащему источнику выдержек не положено.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator
from typing import Any

import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.stream_source import FakeStreamSource
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.revive_settings import SOURCE_PAUSE, SOURCE_TRIES
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install
from torrcast.usecases import source_blame
from torrcast.usecases.source_blame import _asked, _blamed


class RecordingJournal(Silent):
    """Молчащий след, который запоминает одно: что сказали про возврат раздачи."""

    def __init__(self) -> None:
        self.resupplies: list[dict[str, Any]] = []

    def resupply(self, torrent: str, ok: bool) -> None:
        self.resupplies.append({"torrent": torrent, "ok": ok})


@pytest.fixture
def trace() -> Iterator[RecordingJournal]:
    """Ставит записывающий след на время одной проверки и возвращает молчание обратно."""
    sink = RecordingJournal()
    install(sink)
    yield sink
    install(Silent())


def test_a_healthy_source_is_asked_several_times_and_still_not_blamed() -> None:
    """Здоровый источник не виноват, но поверить ему с первого раза нельзя.

    Останавливающаяся служба все три секунды продолжает отвечать и «мёртвой» не выглядит
    ни разу, а показ умирает как раз внутри этого окна. Поэтому вопросов
    :data:`SOURCE_TRIES`, и растянуты они выдержками.
    """
    supply = FakeStreamSource(torrent_hash="hash")
    clock = FakeClock()

    assert _blamed(supply, clock) == ""
    assert len(supply.checks) == SOURCE_TRIES
    assert clock.sleeps == [SOURCE_PAUSE] * (SOURCE_TRIES - 1)


def test_a_source_that_names_its_trouble_is_blamed_at_once_and_asked_no_more() -> None:
    """Ответил бедой - разговор окончен: показ и так уже кончился, тянуть незачем."""
    supply = FakeStreamSource(torrent_hash="hash", trouble="службы раздач не стало")
    clock = FakeClock()

    assert _blamed(supply, clock) == "службы раздач не стало"
    assert len(supply.checks) == 1
    assert clock.sleeps == []


def test_a_restarted_source_is_blamed_even_though_it_answers_that_it_is_fine() -> None:
    """Хорошо стало потому, что раздачу вернули магнитом мы сами, - это и есть улика.

    Такую темноту вешать на приёмник нельзя: он ни при чём.
    """
    supply = FakeStreamSource(torrent_hash="hash", restored=True)
    clock = FakeClock()

    assert _blamed(supply, clock) == phrase("revive.source_restarted")
    assert clock.sleeps == []


def test_a_source_that_is_not_there_at_all_is_never_waited_for() -> None:
    """Источника нет - ждать нечего и некого: выдержек не берётся ни одной."""
    clock = FakeClock()

    assert _blamed(None, clock) == ""
    assert clock.sleeps == []


def test_the_return_of_the_swarm_is_said_once_to_the_viewer_and_once_to_the_trace(
    trace: RecordingJournal, capsys: pytest.CaptureFixture[str]
) -> None:
    """Два разных мнения о том, что сделано с источником, - то же самое, что молчание."""
    supply = FakeStreamSource(torrent_hash="hash", restored=True)

    assert _asked(supply) == ""
    assert trace.resupplies == [{"torrent": "hash", "ok": True}]
    said = phrase("revive.source_back_readded")
    assert capsys.readouterr().out.count(said) == 1


def test_a_healthy_source_says_nothing_to_anyone(
    trace: RecordingJournal, capsys: pytest.CaptureFixture[str]
) -> None:
    """Раздачу никто не возвращал - и говорить не о чем ни зрителю, ни следу."""
    assert _asked(FakeStreamSource(torrent_hash="hash")) == ""
    assert trace.resupplies == []
    assert capsys.readouterr().out == ""


def test_asking_the_source_costs_the_show_nothing_it_does_not_already_know() -> None:
    """Расспрос знает только про источник и часы - ни показа, ни оживления он не тянет.

    Это и есть предмет разреза: до него `_asked`/`_blamed` жили в показе, оживление брало
    их оттуда, и модули были связаны взаимно. Если расспрос снова начнёт зависеть от
    показа, цикл вернётся - и обнаружить его надо здесь, а не на живом запуске.
    """
    tree = ast.parse(inspect.getsource(source_blame))
    named = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert named, "разбор импортов расспроса ничего не нашёл - сторож ослеп"
    assert not [name for name in named if "playback" in name]
