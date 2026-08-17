"""Прогон упаковки снаружи: подъём ffmpeg, замок выкладки, пауза и код возврата."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

import torrcast.usecases.feed_pack._state as _state
from tests.usecases.feed_pack.world import FakeProc, clock, packer, signals
from torrcast.domain.infra_error import InfraError
from torrcast.usecases.feed_pack.packer import Packer

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _Subprocess:
    """Подпроцессы под рукой зеркала: ffmpeg тут не поднимается ни разу."""

    DEVNULL: int = -3
    boom: bool = False
    seen: list[list[str]] = field(default_factory=list)
    TimeoutExpired: type[Exception] = TimeoutError
    SubprocessError: type[Exception] = OSError

    def Popen(self, command: list[str], **kwargs: Any) -> FakeProc:  # noqa: N802
        if self.boom:
            raise FileNotFoundError("ffmpeg")
        self.seen.append(command)
        return FakeProc()


@dataclass
class _Tempfile:
    made: int = 0

    def TemporaryFile(self) -> object:  # noqa: N802
        self.made += 1
        return object()


def _outer(monkeypatch: pytest.MonkeyPatch, boom: bool = False) -> _Subprocess:
    """Подставить подъёму прогона поддельные подпроцессы, временный файл и часы."""
    fake = _Subprocess(boom=boom)
    monkeypatch.setattr(_state, "subprocess", fake)
    monkeypatch.setattr(_state, "tempfile", _Tempfile())
    clock(monkeypatch, now=555.0)
    return fake


def test_the_run_starts_from_a_clean_directory_and_remembers_when(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Каталог прогона расчищается перед стартом, а час старта запоминается.

    Мусор прошлого прогона в своём каталоге - это чужие куски под нашими именами:
    выкладка отдала бы их наружу как свои.
    """
    outer = _outer(monkeypatch)
    run = tmp_path / "out" / "pack"
    run.mkdir(parents=True)
    (run / "v0.ts").write_bytes(b"old")

    made = Packer.start(["ffmpeg", "-i", "src"], tmp_path / "out", run, first=4, at=40.0)

    assert outer.seen == [["ffmpeg", "-i", "src"]]
    assert not (run / "v0.ts").exists(), "мусор прошлого прогона остался в каталоге"
    assert made.began == 555.0 and made.first == 4 and made.at == 40.0
    assert made.edge == 3, "прогон обязан встать перед своим первым куском"


def test_a_missing_ffmpeg_is_an_infrastructure_error_and_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Нет ffmpeg - это внятный отказ инфраструктуры, а не FileNotFoundError зрителю."""
    _outer(monkeypatch, boom=True)

    with pytest.raises(InfraError):
        Packer.start(["ffmpeg"], tmp_path / "out", tmp_path / "out" / "pack")


def test_a_busy_publish_is_skipped_and_never_queued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Второй заход выкладки не ждёт первый: горячий путь важнее лишнего опроса."""
    laid: list[int] = []
    monkeypatch.setattr(
        "torrcast.usecases.feed_pack.packer._lay_out", lambda state, finished: laid.append(1)
    )
    run = packer(tmp_path)

    run.publish()
    assert laid == [1]

    run.publish_lock.acquire()
    run.publish()

    assert laid == [1], "занятый замок значит «решение уже принимают», а не «встань в очередь»"


def test_a_halt_kills_the_process_but_keeps_what_is_already_published(tmp_path: Path) -> None:
    """Пауза на пульте гасит процесс и оставляет выложенное: копить в tmpfs нечего."""
    run = packer(tmp_path, first=0)
    (run.out / "v0.ts").write_bytes(b"piece")

    run.halt()

    assert run.halted is True and run.stopped == "пауза на пульте"
    assert (run.out / "v0.ts").exists(), "пауза не имеет права стирать показанное"
    assert signals(run) == ["terminate"]


def test_the_code_of_the_process_is_answered_as_is(tmp_path: Path) -> None:
    """Код возврата отдаётся как есть: показ отличает живого от трупа именно им."""
    alive = packer(tmp_path)
    assert alive.poll() is None

    dead = packer(tmp_path, proc=FakeProc(code=255))
    assert dead.poll() == 255
