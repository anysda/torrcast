"""Кодировщик целиком: подъём нитки, снятие процесса, начало прогона и итог показа."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode.recoder import Recoder
from torrcast.adapters.recode.recoder_state import _State
from torrcast.adapters.recode.weights import Weights

if TYPE_CHECKING:
    from pathlib import Path


def _recoder(spare: Path, rate: float = 2.0e6, said: list[str] | None = None) -> Recoder:
    lines = grid()
    weights = Weights.of(keys(rate=rate), lines)
    assert weights is not None
    return Recoder(
        source="src",
        audio=0,
        grid=lines,
        spare=spare,
        weights=weights,
        threshold=15.0,
        log=None if said is None else said.append,
    )


def test_the_recoder_keeps_every_field_of_its_state() -> None:
    """Поля живут отдельным файлом, но кодировщик остаётся тем же именем с теми же ручками."""
    assert issubclass(Recoder, _State)
    assert set(_State.__dataclass_fields__) == set(Recoder.__dataclass_fields__)


def test_a_light_film_never_raises_the_thread_at_all(tmp_path: Path) -> None:
    """Тяжёлых кусков нет - перекодировать нечего, и нитку поднимать незачем."""
    said: list[str] = []
    recoder = _recoder(tmp_path, rate=0.5e6, said=said)

    recoder.start()

    assert recoder.thread is None
    assert said == ["тяжёлых кусков нет - перекодировать нечего"]


def test_the_start_says_how_much_of_the_film_is_heavy(tmp_path: Path) -> None:
    """Строка старта - это то, по чему разбирают показ задним числом."""
    said: list[str] = []
    recoder = _recoder(tmp_path / "recode", said=said)
    recoder.stopped = True  # нитка сделает круг и выйдет

    recoder.start()
    assert recoder.thread is not None
    recoder.thread.join(timeout=5.0)

    assert (tmp_path / "recode").is_dir(), "каталог перекода готовится на старте"
    assert "тяжёлых кусков 30 из 30" in said[0]
    assert recoder.began > 0.0


def test_a_new_run_rewinds_the_edge_and_marks_the_head(tmp_path: Path) -> None:
    """Наружу новый прогон не выложил ещё ничего, а старый край остался от прошлого места."""
    recoder = _recoder(tmp_path)
    recoder.edge, recoder.played = 25, 250.0

    recoder.opening(5)

    assert recoder.head == 5
    assert recoder.edge == 4, "иначе выбор захода пропустил бы саму голову"
    assert recoder.played == recoder.grid.start(5), "место показа не ждёт опроса раз в две секунды"
    assert recoder.head_at > 0.0


def test_stopping_wakes_a_paused_process_before_killing_it(tmp_path: Path) -> None:
    """Замерший процесс SIGTERM не обрабатывает вовсе, и снятие стоило бы пяти секунд показа."""
    import signal

    class _Proc:
        def __init__(self) -> None:
            self.signals: list[int] = []

        def send_signal(self, number: int) -> None:
            self.signals.append(number)

    class _Packer:
        def __init__(self) -> None:
            self.proc = _Proc()
            self.stopped: list[str] = []

        def stop(self, keep_files: bool, reason: str) -> None:
            self.stopped.append(reason)

    recoder = _recoder(tmp_path)
    packer: Any = _Packer()
    recoder.packer = packer

    recoder.stop()

    assert recoder.stopped and recoder.packer is None
    assert packer.proc.signals == [signal.SIGCONT], "сперва оживить, потом гасить"
    assert packer.stopped == ["показ окончен"]


def test_the_report_stays_silent_when_there_was_nothing_to_do(tmp_path: Path) -> None:
    """Итог печатается там, где кодировщик работал; на лёгком кино он молчит."""
    assert _recoder(tmp_path, rate=0.5e6).report() == ""

    recoder = _recoder(tmp_path)
    recoder.made, recoder.seconds, recoder.late = 7, 84.0, 2

    assert recoder.report() == "перекодировано 7 кусков (84 с фильма), тяжёлых ушло как есть 2"


@pytest.mark.parametrize(
    "name",
    [
        "holding",
        "note",
        "_head_pending",
        "_hold_head",
        "_hold_bulky",
        "_shrink_touched",
        "_shrink_running",
        "_yield_to_shrink",
        "_pick",
        "_work",
        "_run",
    ],
)
def test_every_occupation_stays_reachable_by_its_old_name(name: str) -> None:
    """Занятия разъехались по файлам, а ручки кодировщика остались теми же."""
    assert callable(getattr(Recoder, name))
