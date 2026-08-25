"""Точечный перекод на диске: его картинка со звуком копии, что лежала под ним."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from torrcast.adapters.ffmpeg.pack_command import pack_command
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.spot_out import spot_out
from torrcast.domain.segment_container import FMP4

#: Кадр AAC 48 кГц в тиках часов MPEG (90 кГц): ровно 1024 сэмпла.
_AAC_TICKS = 1920


def _lay(where: Path, name: str, size: int = 16) -> Path:
    path = where / name
    path.write_bytes(b"x" * size)
    return path


def _pts(piece: Path, stream: str) -> list[int]:
    """Метки пакетов дорожки, тики 90 кГц: сетку AAC видно только в целых тиках."""
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", "packet=pts",
         "-of", "csv=p=0", str(piece)],
        capture_output=True, check=False,
    )  # fmt: skip
    return [
        int(x) for x in done.stdout.decode().replace(",", " ").split() if x.lstrip("-").isdigit()
    ]


def _pack(source: str, run: Path, grid: Grid, slot: int, encode: Encode | None) -> Path:
    run.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        pack_command(source, 0, str(run), grid, slot, grid.start(slot), readrate=0.0,
                     encode=encode, until=-1 if encode is None else slot),
        capture_output=True, check=True,
    )  # fmt: skip
    return run / f"v{slot}.ts"


def _keys(source: str) -> list[float]:
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
         "-show_entries", "frame=pts_time", "-of", "csv=p=0", source],
        capture_output=True, check=False,
    )  # fmt: skip
    return [float(x) for x in done.stdout.decode().replace(",", " ").split() if x]


def test_the_laid_piece_keeps_the_frame_grid_of_the_copy(clip_mp4: str, tmp_path: Path) -> None:
    """🔴 Ради этого написано: сетка AAC уложенного куска - сетка КОПИИ, а не второго прогона.

    Точечный перекод - отдельный ffmpeg на один кусок, и его кодировщик начинает сетку от
    своего ``-ss``. Соседи по каталогу лежат копией одного прогона, поэтому без склейки на
    каждом стыке звук рвётся: замер на уложенном каталоге двухчасовой картины - фаза 540
    тиков у всех копий против 270, 690, 1170, 330, 810, 1230 у точечных перекодов и дыра
    47.3-54.7 мс на стыке.

    Проба падает ровно на этом дефекте: снимите склейку - и фаза уложенного куска станет
    фазой перекода, а не копии.
    """
    grid = Grid.on_keyframes(_keys(clip_mp4), 60.0, 10.0, origin=0.05)
    copy = _pack(clip_mp4, tmp_path / "copy", grid, 0, None)
    laid = _pack(clip_mp4, tmp_path / "spot", grid, 2, Encode(preset="ultrafast", mbit=2.0))
    copy_here = tmp_path / "copy" / "v2.ts"
    bare = _pts(laid, "a:0")[0]

    assert spot_out(2, laid, copy_here, cap=1 << 30) is True

    assert _pts(laid, "a:0")[0] % _AAC_TICKS == _pts(copy_here, "a:0")[0] % _AAC_TICKS, (
        "звук уложенного куска остался на сетке своего прогона - стык с соседями рвётся"
    )
    assert bare % _AAC_TICKS != _pts(copy_here, "a:0")[0] % _AAC_TICKS, (
        "сетки перекода и копии совпали сами: проба не может покраснеть на своём предмете"
    )
    assert _pts(laid, "v:0")[0] != _pts(copy, "v:0")[0], "картинка уехала вместе со звуком"


def test_the_picture_comes_from_the_recode_and_the_sound_from_the_copy(tmp_path: Path) -> None:
    """Порядок дорожек: картинка у перекода, звук у копии, а не наоборот."""
    seen: list[tuple[str, str]] = []

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        seen.append((video.name, audio.name))
        dst.write_bytes(b"m" * 20)
        return True

    laid, copy = _lay(tmp_path, "v7.ts", 18), _lay(tmp_path, "a7.ts", 100)

    assert spot_out(7, laid, copy, 50, merge=merge, shift_of=lambda *a: 0.0) is True
    assert seen == [("v7.ts", "a7.ts")], "звук уложенного куска взят не у копии"
    assert laid.read_bytes() == b"m" * 20 and not (tmp_path / "mixv7.ts").exists()


def test_the_shift_between_the_two_passes_reaches_the_merge(tmp_path: Path) -> None:
    """Сдвиг лент копии и перекода доезжает до склейки: без него стык уедет на кадр."""
    shifts: list[float] = []

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        shifts.append(kwargs["shift"])
        dst.write_bytes(b"m")
        return True

    spot_out(3, _lay(tmp_path, "v3.ts"), _lay(tmp_path, "a3.ts"), 50,
             merge=merge, shift_of=lambda *a: 0.0417)  # fmt: skip

    assert shifts == [0.0417]


def test_a_merge_that_did_not_happen_leaves_the_bare_recode(tmp_path: Path) -> None:
    """Склейки нет - на диске остаётся голый перекод, как лежал раньше."""
    laid, copy = _lay(tmp_path, "v1.ts", 18), _lay(tmp_path, "a1.ts")

    assert (
        spot_out(1, laid, copy, 50, merge=lambda *a, **k: False, shift_of=lambda *a: 0.0) is False
    )
    assert laid.read_bytes() == b"x" * 18 and not (tmp_path / "mixv1.ts").exists()


def test_a_merge_heavier_than_the_ceiling_is_thrown_away(tmp_path: Path) -> None:
    """Склейка за потолком приёмника не ложится: такой кусок показ с диска не возьмёт."""

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        dst.write_bytes(b"m" * 80)
        return True

    laid, copy = _lay(tmp_path, "v2.ts", 18), _lay(tmp_path, "a2.ts")

    assert spot_out(2, laid, copy, 50, merge=merge, shift_of=lambda *a: 0.0) is False
    assert laid.read_bytes() == b"x" * 18, "перекод подменили склейкой за потолком"
    assert not (tmp_path / "mixv2.ts").exists(), "склейка за потолком осталась лежать"


def test_an_empty_merge_is_not_taken_for_a_light_one(tmp_path: Path) -> None:
    """Пустая склейка легче любого потолка - и всё же это не кусок, а ноль байт."""

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        dst.write_bytes(b"")
        return True

    laid, copy = _lay(tmp_path, "v4.ts", 18), _lay(tmp_path, "a4.ts")

    assert spot_out(4, laid, copy, 50, merge=merge, shift_of=lambda *a: 0.0) is False
    assert laid.read_bytes() == b"x" * 18


def test_the_warm_merge_is_muxed_by_the_container_of_the_receiver(tmp_path: Path) -> None:
    """Тёплый путь склеивает тем же муксером, что и живой: файл остаётся именем куска.

    На живом пути контейнер уже едет из профиля приёмника, а здесь оставалось умолчание
    завода - то есть на fMP4 склейка прогрева собиралась бы mpegts под ``.m4s``.
    """
    seen: list[object] = []

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        seen.append(kwargs.get("container"))
        dst.write_bytes(b"m" * 10)
        return True

    laid, copy = tmp_path / "v7.m4s", tmp_path / "a7.m4s"
    laid.write_bytes(b"v" * 20)
    copy.write_bytes(b"a" * 20)

    assert spot_out(7, laid, copy, 100, FMP4, merge=merge, shift_of=lambda *a: 0.0) is True
    assert seen == [FMP4]
