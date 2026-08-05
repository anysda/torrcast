"""Карта опорных кадров: mkv по ``Cues``, mp4 по ``stss``, и обе — одинаковая правда.

Проверяется не «работает вообще», а три вещи, каждая из которых уже стоила проекту суток:

* **цена**. У холодной раздачи каждый лишний Range-запрос и каждый лишний мегабайт —
  это секунды старта (§7.2 SPEC-v2), поэтому тесты считают запросы и байты, а не точки.
* **правда**. Карта сверяется с ``ffprobe``, который читает тот же файл честным перебором
  пакетов. Расходиться им нельзя: по карте режутся сегменты.
* **одинаковость**. Один и тот же битстрим в mkv и в mp4 обязан дать одну и ту же карту —
  иначе «сетка по опорным кадрам» значит разное в зависимости от контейнера.
"""

from __future__ import annotations

import itertools
import subprocess
from pathlib import Path

import pytest

from torrcast import InfraError
from torrcast.keymap import HEAD_PEEK, Reader, keyframes, video_track
from torrcast.mkv import CUES_CHUNK, HEAD_BYTES


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[tuple[int, int]]]:
    """Отдаём файл кусками, как рой: считаем каждый запрос и его размер."""
    asked: dict[str, list[tuple[int, int]]] = {}

    def read(self: Reader, offset: int, size: int) -> bytes:
        asked.setdefault(self.url, []).append((offset, size))
        data = Path(self.url).read_bytes()[offset : offset + size]
        self.taken += len(data)
        self.requests += 1
        return data

    monkeypatch.setattr(Reader, "read", read)
    return asked


def probe_keys(path: str) -> list[float]:
    """Опорные кадры честным перебором пакетов — то, с чем карта обязана совпасть."""
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-skip_frame", "nokey",
         "-show_entries", "frame=pts_time", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return [float(line.rstrip(",")) for line in done.stdout.split() if line.strip(",")]


def probe_offsets(path: str) -> list[int]:
    """Где опорные кадры лежат в файле — по мнению ffprobe."""
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-skip_frame", "nokey",
         "-show_entries", "frame=pkt_pos", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return [int(line.rstrip(",")) for line in done.stdout.split() if line.strip(",").isdigit()]


def test_mkv_two_requests_and_small_head(
    served: dict[str, list[tuple[int, int]]], clip: str
) -> None:
    """Карта mkv снимается двумя заходами: маленькая голова и один кусок с места Cues."""
    found = keyframes(clip)
    assert [size for _, size in served[clip]] == [HEAD_PEEK, CUES_CHUNK]
    assert found.requests == 2
    assert found.duration > 0
    assert found.points
    assert video_track(found.points) in {p.track for p in found.points}


def test_mkv_falls_back_to_full_head(
    served: dict[str, list[tuple[int, int]]], clip: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Маленького куска не хватило — берём полную голову, а не сдаёмся."""
    monkeypatch.setattr("torrcast.keymap.HEAD_PEEK", 64)
    keyframes(clip)
    assert [size for _, size in served[clip]][:2] == [64, HEAD_BYTES]


def test_unknown_container_is_infra_error(
    served: dict[str, list[tuple[int, int]]], tmp_path: Path
) -> None:
    """Ни mkv, ни mp4 — честная ошибка, по которой показ берёт ровную сетку."""
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"\x00" * (1 << 16))
    with pytest.raises(InfraError):
        keyframes(str(junk))


def test_mp4_map_matches_ffprobe(served: dict[str, list[tuple[int, int]]], clip_mp4: str) -> None:
    """Карта mp4 — те же кадры и те же байты, что видит ffprobe, читающий файл целиком."""
    found = keyframes(clip_mp4)
    assert [round(p.at, 3) for p in found.points] == [round(x, 3) for x in probe_keys(clip_mp4)]
    assert [p.offset for p in found.points] == probe_offsets(clip_mp4)


def test_mp4_with_b_frames_and_edit_list(
    served: dict[str, list[tuple[int, int]]], clip_mp4_bframes: str
) -> None:
    """B-кадры и список правок: ``ctts`` и ``elst`` учтены — иначе карта уедет на кадры.

    Без ``ctts`` времена получились бы временами декодирования, без ``elst`` — сдвинутыми
    на пару кадров вперёд. И то и другое ломает сетку молча: границы просто перестают
    попадать на опорные кадры, а виден этот брак только на живом ТВ.
    """
    found = keyframes(clip_mp4_bframes)
    assert [round(p.at, 3) for p in found.points] == [
        round(x, 3) for x in probe_keys(clip_mp4_bframes)
    ]


def test_mp4_moov_in_tail_costs_no_mdat(
    served: dict[str, list[tuple[int, int]]], clip_mp4_tail: str
) -> None:
    """``moov`` в хвосте — карта снимается, но ``mdat`` не читается ни одним куском.

    Иначе «взять карту» означало бы скачать фильм: у раздачи в 2 ГБ это и есть ``mdat``.
    """
    found = keyframes(clip_mp4_tail)
    assert found.points
    assert found.taken < Path(clip_mp4_tail).stat().st_size / 2


def test_the_same_film_gives_the_same_map(
    served: dict[str, list[tuple[int, int]]], clip: str, clip_mp4: str
) -> None:
    """Один битстрим, два контейнера — одна карта GOP: сетка не зависит от упаковки.

    ⚠️ Секунда в секунду карты НЕ совпадают, и это правда файла, а не брак разбора:
    ремукс mkv в mp4 вставляет перед видео пустую правку в 6 мс, чтобы выровнять его со
    звуком, и ffprobe в каждом контейнере называет свои числа — те же, что и мы. Одинаково
    в них другое: длины GOP, то есть ровно то, из чего строятся границы сегментов.
    """
    inside = keyframes(clip)
    outside = keyframes(clip_mp4)
    track = video_track(inside.points)
    theirs = [p.at for p in inside.points if p.track == track]
    ours = [p.at for p in outside.points]
    assert len(ours) == len(theirs)
    assert [round(b - a, 3) for a, b in itertools.pairwise(theirs)] == [
        round(b - a, 3) for a, b in itertools.pairwise(ours)
    ]
    assert max(abs(a - b) for a, b in zip(theirs, ours, strict=True)) < 0.04  # меньше кадра


def test_map_is_deterministic(served: dict[str, list[tuple[int, int]]], clip_mp4: str) -> None:
    """Дважды снятая карта совпадает до байта: на ней держится детерминированность нарезки."""
    assert keyframes(clip_mp4).points == keyframes(clip_mp4).points
