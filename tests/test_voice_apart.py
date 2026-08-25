"""Русская дорожка отдельным файлом рядом с видео: та же сетка и нулевой стык звука.

Проверяется настоящим ffmpeg на настоящих кусках, потому что предмет тут ровно машинный:
второй вход обязан лечь на СУЩЕСТВУЮЩУЮ сетку кусков, не сдвинув ни одного реза, и не
принести с собой ни одной дыры в звуке. Сдвинутая граница делает ненаходимым каждый уже
прогретый каталог, а дыра звука стоит приёмнику секунд: через 3.3 с сухого демуксера
приставка сносит свой звуковой тракт.
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path

import pytest

from tests.conftest import CLIP_SECONDS, band_db
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.domain.hls_settings import PACK_LIST

#: Тик ленты mpegts: 90 кГц. Стык меряется в них, а не «на глаз».
_TICK = 90_000


def _grid() -> Grid:
    return Grid.uniform(float(CLIP_SECONDS))


def _pack(source: str, run: Path, slot: int, until: int, voice: str = "") -> list[list[str]]:
    """Один прогон упаковки и его список резов; ``at`` равен границе - вход ровный."""
    run.mkdir(parents=True, exist_ok=True)
    grid = _grid()
    command = ffmpeg_pack_command(
        source, 0, str(run), grid, slot, grid.start(slot), readrate=0.0, until=until, voice=voice
    )
    subprocess.run(command, check=True, capture_output=True, timeout=300)
    with (run / PACK_LIST).open(encoding="utf-8") as rows:
        return [row for row in csv.reader(rows) if row]


def _audio_edges(path: Path) -> tuple[int, int, int]:
    """Первый и последний тик звука в куске и частота дискретизации потока.

    Частота читается из ПОТОКА намеренно: без неё кадр AAC считается по 48 кГц, каталог
    со звуком 44.1 кГц разбирается как сотня отдельных прогонов с дырами - и прибор врёт
    красным на сплошном звуке.
    """
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_packets", "-show_streams",
         "-show_entries", "packet=pts,duration:stream=sample_rate", "-of", "csv=p=1", str(path)],
        check=True, capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    packets, rate = [], 0
    for line in done.stdout.splitlines():
        parts = line.strip().split(",")
        if parts[0] == "packet":
            packets.append((int(parts[1]), int(parts[2])))
        elif parts[0] == "stream":
            rate = int(parts[1])
    assert packets and rate, f"ffprobe не нашёл звука в {path.name}"
    return packets[0][0], packets[-1][0] + packets[-1][1], rate


def test_the_second_input_does_not_move_a_single_cut(
    clip: str, clip_voice: str, tmp_path: Path
) -> None:
    """🔴 Резы сетки на двух входах ровно те же, что на одном - до тысячной доли.

    Это и есть главный предмет работы. Сдвинься хоть одна граница - и каждый уже
    прогретый каталог перестаёт находиться под своим именем, потому что отпечаток
    каталога считается ровно по границам.
    """
    alone = _pack(clip, tmp_path / "alone", 0, -1)
    together = _pack(clip, tmp_path / "together", 0, -1, voice=clip_voice)

    assert [row[0] for row in together] == [row[0] for row in alone], "разъехались имена кусков"
    for mine, theirs in zip(together, alone, strict=True):
        assert float(mine[1]) == pytest.approx(float(theirs[1]), abs=0.001)
        assert float(mine[2]) == pytest.approx(float(theirs[2]), abs=0.001)


def test_the_tail_of_a_longer_track_does_not_glue_itself_to_the_last_piece(
    clip: str, clip_voice: str, tmp_path: Path
) -> None:
    """Дорожка длиннее видео обрывается на конце фильма, а не висит хвостом.

    Прогон живого показа ``-to`` не называет вовсе, и без своей меры на втором входе
    хвост дорожки уезжает зрителю внутри последнего куска: замер даёт 1078 звуковых
    кадров вместо 431, то есть 25 с звука в куске, который обещает 10.
    """
    rows = _pack(clip, tmp_path / "together", 0, -1, voice=clip_voice)
    last = tmp_path / "together" / rows[-1][0]

    _, ended, _ = _audio_edges(last)
    assert ended / _TICK <= CLIP_SECONDS + 1.5, (
        f"звук последнего куска тянется до {ended / _TICK:.2f} с при фильме {CLIP_SECONDS} с"
    )


def test_the_show_plays_the_track_from_the_second_file(
    clip: str, clip_voice: str, tmp_path: Path
) -> None:
    """Зрителю уехал звук ВТОРОГО файла, и уехал на своём месте ленты, а не со сдвигом."""
    alone = _pack(clip, tmp_path / "alone", 0, -1)
    together = _pack(clip, tmp_path / "together", 0, -1, voice=clip_voice)
    head, tail = tmp_path / "together" / together[0][0], tmp_path / "together" / together[-1][0]

    assert band_db(tmp_path / "alone" / alone[0][0], 440) > band_db(
        tmp_path / "alone" / alone[0][0], 660
    ), "стенду нужен ролик, у которого свой звук отличим от отдельной дорожки"
    assert band_db(head, 660) > band_db(head, 440) + 10, "в первом куске играет звук видео"
    assert band_db(tail, 1320) > band_db(tail, 660) + 10, "дорожка уехала сдвинутой по ленте"


def test_a_second_run_starts_the_sound_exactly_where_the_first_stopped(
    clip: str, clip_voice: str, tmp_path: Path
) -> None:
    """🔴 Стык двух прогонов на двух входах не хуже, чем на одном - в тиках, а не «на глаз».

    Кадровая сетка AAC отсчитывается от ``-ss`` прогона, поэтому стык двух прогонов -
    единственное место, где дыра в звуке может родиться сама. Приёмнику она стоит не
    миллисекунд: через 3.3 с сухого демуксера приставка сносит звуковой тракт и платит
    секундами. Второй вход обязан не добавить к этому стыку ничего.
    """
    seam = 2

    def gap(where: Path, voice: str) -> int:
        head = _pack(clip, where / "head", 0, seam, voice=voice)
        _pack(clip, where / "tail", seam + 1, -1, voice=voice)
        _, ended, _ = _audio_edges(where / "head" / head[seam][0])
        began, _, _ = _audio_edges(where / "tail" / f"v{seam + 1}.ts")
        return began - ended

    alone = gap(tmp_path / "alone", "")
    together = gap(tmp_path / "together", clip_voice)

    assert together == alone, (
        f"второй вход изменил стык прогонов: {together} тик против {alone} "
        f"({(together - alone) * 1000 / _TICK:+.2f} мс)"
    )
