"""Дочитал ли прогон вход: код возврата тут не судья, судит обещание сетки."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import FakeProc, grid, lay, packer
from torrcast.domain.hls_settings import PACK_LIST
from torrcast.usecases.feed_pack.packer_finished import _cuts, _drift, _finished

if TYPE_CHECKING:
    from pathlib import Path


def _list(run: Path, *rows: tuple[str, float, float]) -> None:
    run.joinpath(PACK_LIST).write_text(
        "".join(f"{name},{began:.3f},{end:.3f}\n" for name, began, end in rows), encoding="utf-8"
    )


def test_a_living_or_killed_run_never_counts_as_read_to_the_end(tmp_path: Path) -> None:
    """Жив или убит - вход не дочитан: спрашивать сетку тут ещё не о чем."""
    assert _finished(packer(tmp_path)) is False
    assert _finished(packer(tmp_path, proc=FakeProc(code=255))) is False


def test_a_short_last_piece_makes_the_zero_of_ffmpeg_a_lie(tmp_path: Path) -> None:
    """Ноль от ffmpeg на недописанном куске - это обрыв входа, а не конец фильма.

    Замер: 108 обрывов, ноль вышел 4 раза, и трижды хвост был дописан не до конца.
    """
    run = packer(tmp_path, proc=FakeProc(code=0), grid=grid())
    lay(run.run, 0)
    lay(run.run, 1)
    _list(run.run, ("v0.ts", 0.0, 10.0), ("v1.ts", 10.0, 14.0))

    assert _finished(run) is False, "недобор шесть секунд выдан за дочитанный вход"


def test_a_last_piece_within_the_tolerance_is_the_honest_end_of_the_film(tmp_path: Path) -> None:
    """Недобор в доли секунды законен: длительность берут из контейнера, а поток кончается."""
    run = packer(tmp_path, proc=FakeProc(code=0), grid=grid())
    lay(run.run, 0)
    _list(run.run, ("v0.ts", 0.0, 9.7))

    assert _finished(run) is True


def test_a_closed_piece_without_a_line_is_believed_to_nobody(tmp_path: Path) -> None:
    """Кусок есть, а строки о нём нет: список ведёт тот же ffmpeg - верить тут нечему."""
    run = packer(tmp_path, proc=FakeProc(code=0), grid=grid())
    lay(run.run, 0)

    assert _finished(run) is False


def test_the_answer_is_counted_once_and_never_re_asked(tmp_path: Path) -> None:
    """Ответ считается один раз: у мёртвого прогона файлы и список уже не меняются."""
    run = packer(tmp_path, proc=FakeProc(code=0), grid=grid())
    lay(run.run, 0)
    _list(run.run, ("v0.ts", 0.0, 9.9))

    assert _finished(run) is True
    _list(run.run, ("v0.ts", 0.0, 1.0))

    assert _finished(run) is True and run.whole is True


def test_pieces_beyond_the_pass_are_not_counted_as_a_break(tmp_path: Path) -> None:
    """Огрызок за ``-to`` короче своего места по замыслу, а не по аварии."""
    run = packer(tmp_path, proc=FakeProc(code=0), grid=grid(), last=0)
    lay(run.run, 0)
    lay(run.run, 1)
    _list(run.run, ("v0.ts", 0.0, 9.9), ("v1.ts", 10.0, 11.0))

    assert _finished(run) is True


def test_the_cut_list_is_read_as_ffmpeg_wrote_it_and_junk_is_skipped(tmp_path: Path) -> None:
    """Список нарезки читается строкой в строку; кривые строки не выдумываются."""
    run = packer(tmp_path)
    run.run.joinpath(PACK_LIST).write_text(
        "v0.ts,0.000,10.000\nмусор\nv1.ts,10.000,20.000,\n", encoding="utf-8"
    )

    assert _cuts(run) == [(0, 0.0, 10.0), (1, 10.0, 20.0)]


def test_no_list_at_all_is_an_empty_answer_and_no_drift(tmp_path: Path) -> None:
    """Списка нет - расхождения не выдумываем: ноль означает «манифест не врёт»."""
    run = packer(tmp_path)

    assert _cuts(run) == [] and _drift(run, grid()) == 0.0


def test_the_drift_skips_the_first_row_and_subtracts_the_start_of_the_timeline(
    tmp_path: Path,
) -> None:
    """Первая строка врёт нулём, а метки сдвинуты на начало ленты: и то и другое учтено."""
    run = packer(tmp_path, first=0)
    lines = grid()
    assert lines.origin == 0.0, "стенд взял сетку со сдвигом - замер ниже уже не про то"
    # Первая строка расходится с сеткой на пять секунд и в счёт не идёт, вторая - на 0.4.
    _list(run.run, ("v0.ts", 5.0, 10.0), ("v1.ts", 10.4, 20.0), ("v2.ts", 20.0, 30.0))

    assert round(_drift(run, lines), 3) == 0.4
