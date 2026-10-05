"""TC-1405: последний кусок фильма при замке выкладки, занятом параллельным проходом.

Гонка воспроизводится детерминированно (:class:`Contended`): чужой проход держит замок
в своём потоке, пока его не ждут. Вердикт «файла не будет» - это 404 зрителю, и выносить
его по выкладке, которая выхода ffmpeg не дождалась, нельзя.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.contended import contend
from tests.usecases.feed_pack.world import FakeProc, feed, lay, packer, tract

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
