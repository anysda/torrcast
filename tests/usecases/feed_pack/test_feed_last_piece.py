"""TC-1405: последний кусок фильма при замке выкладки, занятом параллельным проходом.

Гонка воспроизводится детерминированно (:class:`Contended`): чужой проход держит замок
в своём потоке, пока его не ждут. Вердикт «файла не будет» - это 404 зрителю, и выносить
его по выкладке, которая выхода ffmpeg не дождалась, нельзя.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.contended import contend
from tests.usecases.feed_pack.world import FakeProc, feed, lay, packer, tract
from torrcast.usecases.feed_pack.feed_steer import _steer

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.adapters.stream_pack.packer import Packer
    from torrcast.usecases.feed_pack.feed import Feed


def _tail_written(tmp_path: Path, proc: FakeProc) -> tuple[Feed, Packer]:
    """Показ, чей прогон дописал куски 0-2; ``proc`` - вышел ли уже ffmpeg."""
    tract()
    show = feed(tmp_path)
    run = packer(tmp_path, first=0, out=show.out, proc=proc)
    show.packer = run
    for slot in range(3):
        lay(run.run, slot)
    return show, run


def test_the_last_piece_waits_for_the_parallel_pass_instead_of_a_404(tmp_path: Path) -> None:
    """ffmpeg уже вышел, замок держит параллельный проход: выкладка его ждёт."""
    show, run = _tail_written(tmp_path, FakeProc(code=0))
    lock = contend(run)
    try:
        hope = _steer(show, 2, lambda slot: None)
    finally:
        lock.close()

    assert hope is True and (show.out / "v2.ts").exists(), (
        "выкладка ушла ни с чем мимо чужого прохода, и последний кусок получил 404"
    )
    assert lock.waited.is_set()


def test_ffmpeg_leaving_while_the_publish_is_turned_away_is_still_no_404(
    tmp_path: Path,
) -> None:
    """ffmpeg вышел ровно в миг отказа замка: выкладка решила «не ждать» живому процессу.

    Окно между выкладкой и вердиктом: второй ``poll()`` уже видит выход, и край, не
    дождавшийся последнего прохода, читается как «файла не будет».
    """
    proc = FakeProc()
    show, run = _tail_written(tmp_path, proc)

    def exits() -> None:
        proc.code = 0

    lock = contend(run, on_refused=exits)
    try:
        hope = _steer(show, 2, lambda slot: None)
    finally:
        lock.close()

    assert lock.refused >= 1, "прибор не попал в окно: выкладка ни разу не получила отказ"
    assert hope is True and (show.out / "v2.ts").exists(), (
        "вердикт вынесен по выкладке, которая выхода ffmpeg не дождалась: 404"
    )


def test_stopping_the_show_never_waits_for_the_parallel_pass(tmp_path: Path) -> None:
    """Остановка зовётся под замком ленты: ждать чужой проход (ужатие до ~50 с) ей нельзя."""
    show, run = _tail_written(tmp_path, FakeProc())
    lock = contend(run)
    try:
        show.stop()
    finally:
        lock.close()

    assert not lock.waited.is_set(), "остановка встала ждать чужой проход выкладки"
    assert not run.run.exists(), "снятый прогон не убрал свой каталог"
