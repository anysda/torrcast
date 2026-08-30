"""Прогон упаковки снаружи: подъём ffmpeg, замок выкладки, пауза и код возврата."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from tests.usecases.feed_pack.world import FakeProc, hand, packer, signals
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.domain.infra_error import InfraError

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _Spawn:
    """Подъём процесса под рукой зеркала: ffmpeg тут не поднимается ни разу."""

    boom: bool = False
    seen: list[list[str]] = field(default_factory=list)

    def __call__(self, command: list[str], **kwargs: Any) -> FakeProc:
        if self.boom:
            raise FileNotFoundError("ffmpeg")
        self.seen.append(command)
        return FakeProc()


def _log() -> Any:
    """Временный файл под брань ffmpeg: на стенде он никому не нужен."""
    return io.BytesIO()


def _outer(boom: bool = False) -> _Spawn:
    """Подъём процесса под рукой зеркала: ffmpeg тут не поднимается ни разу."""
    return _Spawn(boom=boom)


def test_the_run_starts_from_a_clean_directory_and_remembers_when(tmp_path: Path) -> None:
    """Каталог прогона расчищается перед стартом, а час старта запоминается.

    Мусор прошлого прогона в своём каталоге - это чужие куски под нашими именами:
    выкладка отдала бы их наружу как свои.
    """
    outer = _outer()
    run = tmp_path / "out" / "pack"
    run.mkdir(parents=True)
    (run / "v0.ts").write_bytes(b"old")

    made = Packer.start(
        ["ffmpeg", "-i", "src"],
        tmp_path / "out",
        run,
        first=4,
        at=40.0,
        spawn=outer,
        log_file=_log,
        now=hand(555.0).monotonic,
    )

    assert outer.seen == [["ffmpeg", "-i", "src"]]
    assert not (run / "v0.ts").exists(), "мусор прошлого прогона остался в каталоге"
    assert made.began == 555.0 and made.first == 4 and made.at == 40.0
    assert made.edge == 3, "прогон обязан встать перед своим первым куском"


def test_a_missing_ffmpeg_is_an_infrastructure_error_and_not_a_traceback(tmp_path: Path) -> None:
    """Нет ffmpeg - это внятный отказ инфраструктуры, а не FileNotFoundError зрителю."""
    outer = _outer(boom=True)

    with pytest.raises(InfraError):
        Packer.start(
            ["ffmpeg"], tmp_path / "out", tmp_path / "out" / "pack", spawn=outer, log_file=_log
        )


def test_a_busy_publish_is_skipped_and_never_queued(tmp_path: Path) -> None:
    """Второй заход выкладки не ждёт первый: горячий путь важнее лишнего опроса."""
    laid: list[int] = []

    class Counted(Packer):
        """Прогон, у которого сама выкладка ничего не делает: меряется замок вокруг неё."""

        def _publish(self) -> None:
            laid.append(1)

    run = packer(tmp_path, kind=Counted)

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

    assert run.halted is True and run.stopped == "paused from the remote"
    assert (run.out / "v0.ts").exists(), "пауза не имеет права стирать показанное"
    assert signals(run) == ["terminate"]


def test_the_code_of_the_process_is_answered_as_is(tmp_path: Path) -> None:
    """Код возврата отдаётся как есть: показ отличает живого от трупа именно им."""
    alive = packer(tmp_path)
    assert alive.poll() is None

    dead = packer(tmp_path, proc=FakeProc(code=255))
    assert dead.poll() == 255
