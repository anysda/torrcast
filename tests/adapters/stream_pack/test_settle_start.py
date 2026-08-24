"""Проверяет отвод захода назад: заход не имеет права проскочить свою границу."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.settle_start import SEEK_BACK_TRIES, settle_start
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install

#: Шаг сетки в пробах ниже. Ровный и такой же, какой берёт живой показ.
STEP = 10.0


class _Spy(Silent):
    """Молчащая лента, которая помнит отметки: отвод обязан оставлять след."""

    def __init__(self) -> None:
        self.marks: list[tuple[str, dict[str, Any]]] = []

    def mark(self, name: str, **facts: Any) -> None:
        self.marks.append((name, facts))


class _Demuxer:
    """Демуксер, который садится на точку своего списка: ``ahead`` - в какую сторону.

    Вперёд садится mpegts и файл, чей индекс врёт: место посадки к границам сетки
    отношения не имеет, и между двумя точками плёнку взять неоткуда. Назад - здоровый
    mkv, у которого докатка есть всегда и лечить нечего.
    """

    def __init__(self, points: list[float], ahead: bool = True) -> None:
        self.points = points
        self.ahead = ahead
        self.asked: list[float] = []

    def __call__(self, source_url: str, at: float, *rest: Any) -> float:
        self.asked.append(at)
        if self.ahead:
            return next((point for point in self.points if point >= at), self.points[-1])
        return max((point for point in self.points if point <= at), default=self.points[0])


def test_a_run_standing_before_its_boundary_is_left_alone() -> None:
    """Посадка назад - это здоровый файл: ни одного лишнего пробного прогона."""
    demuxer = _Demuxer([0.0, 8.0, 18.0, 28.0], ahead=False)
    assert settle_start("вход", 20.0, start=demuxer) == (20.0, 18.0)
    assert demuxer.asked == [20.0], "здоровому файлу отвод не нужен и не оплачивается"


def test_a_run_overshooting_its_boundary_is_pulled_back() -> None:
    """Посадка вперёд - заход отводится назад, пока не встанет не позже границы."""
    spy = _Spy()
    install(spy)
    demuxer = _Demuxer([0.0, 8.851, 20.937, 31.364])
    seek, stood = settle_start("вход", 30.0, start=demuxer)
    assert stood == 20.937, "прогон обязан встать НЕ ПОЗЖЕ границы - иначе плёнки нет"
    assert demuxer.asked == [30.0, 20.0], "первой спрашивается сама граница, потом отвод"
    assert seek == 20.0
    said = [facts for name, facts in spy.marks if name == "заход отведён от границы"]
    assert said and said[0]["граница"] == 30.0 and said[0]["встали"] == 20.937


def test_the_step_of_the_pull_back_doubles() -> None:
    """Ближний отвод часто приводит туда же: шаг растёт, пока не перешагнёт провал."""
    demuxer = _Demuxer([0.0, 385.613, 454.921])
    seek, stood = settle_start("вход", 450.0, start=demuxer)
    assert stood == 385.613
    assert seek == pytest.approx(450.0 - STEP * 2 ** (len(demuxer.asked) - 2))
    assert len(demuxer.asked) <= SEEK_BACK_TRIES + 1, "прогонов больше, чем разрешено"


def test_a_film_that_cannot_be_entered_earlier_keeps_the_old_entry() -> None:
    """Отойти не вышло - заход остаётся прежним, и об этом говорится вслух.

    Ровный провал шире отвода - это фильм, в котором перемотка мертва целыми минутами.
    Платить за него пробными прогонами без конца дороже самой дыры, а тихо оставлять
    прежний заход нельзя: дыра эта видна зрителю.
    """
    spy = _Spy()
    install(spy)
    demuxer = _Demuxer([500.0, 5000.0])
    assert settle_start("вход", 450.0, start=demuxer) == (450.0, 500.0)
    assert [name for name, _ in spy.marks] == ["отвести заход от границы не вышло"]


def test_the_pull_back_stops_at_the_start_of_the_film() -> None:
    """Ниже нуля отводить некуда: там заход и так стоит на начале ленты."""
    demuxer = _Demuxer([7.0, 40.0])
    seek, stood = settle_start("вход", 5.0, start=demuxer)
    assert (seek, stood) == (5.0, 7.0)
    assert demuxer.asked == [5.0, 0.0], "нулём отвод кончается, а не крутится дальше"


@pytest.mark.ffmpeg
def test_the_piece_of_the_boundary_really_starts_on_the_boundary(
    clip_ts: str, tmp_path: Path
) -> None:
    """🔴 Мера всей карточки, настоящим ffmpeg: кусок границы начинается границей.

    У mpegts ``-ss`` уводит демуксер ВПЕРЁД, на следующий опорный кадр, - тот самый уезд,
    из-за которого кусок под именем границы начинался позже неё, а приёмник упирался в
    дыру. Здесь прогон поднимается по-настоящему, и меряется то, что уехало бы зрителю.

    Отрицательная проба той же командой: убрать ``seek`` из сборки (или спросить место
    захода прежним :func:`pack_start`) - и первый пакет куска уезжает за границу.
    """
    grid = Grid.uniform(60.0, STEP)
    slot = 2
    run = tmp_path / "pack"
    run.mkdir()
    seek, at = settle_start(clip_ts, grid.start(slot))
    assert at <= grid.start(slot), "отвод не сработал - мерить дальше нечего"
    subprocess.run(
        ffmpeg_pack_command(clip_ts, 0, str(run), grid, slot, at, readrate=0.0, seek=seek),
        check=True,
        capture_output=True,
    )
    assert _first_frame(run / f"v{slot}.ts") == pytest.approx(grid.start(slot), abs=0.05)


def _first_frame(path: Path) -> float:
    """Метка первого кадра куска, секунды."""
    found = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
         "packet=pts_time", "-of", "csv=p=0", "-read_intervals", "%+#1", str(path)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return float(found.stdout.strip().splitlines()[0].split(",")[0])
