"""Таблицы сэмплов ``stbl``: какие кадры опорные, когда они и где лежат в файле.

Зовёт это снятие карты (:func:`torrcast.domain.frames.mp4.keys`) - и только оно.
"""

from __future__ import annotations

import struct

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.frames.mp4._window import _find, _full, _table, _Window
from torrcast.domain.infra_error import InfraError


def _sync_samples(window: _Window, stbl: tuple[int, int], total: int) -> list[int]:
    """Номера опорных сэмплов (с единицы). Нет ``stss`` — опорным считается каждый."""
    found = _find(window, *stbl, b"stss")
    if found is None:
        return list(range(1, total + 1))
    at, count = _table(window, *found, 4)
    raw = window.take(at, count * 4)
    return list(struct.unpack(f">{count}I", raw))


def _sample_times(window: _Window, stbl: tuple[int, int], wanted: list[int]) -> list[int]:
    """Время декодирования нужных сэмплов, по сжатой таблице ``stts``.

    ⚠️ Разбор идёт **слиянием** двух отсортированных списков, а не поиском по таблице на
    каждый кадр. Ровно на этом месте карта mkv однажды стала квадратичной и стоила 18.5 с
    чистого процессора — повторять эту цену незачем.
    """
    found = _find(window, *stbl, b"stts")
    if found is None:
        raise InfraError(phrase("frames.mp4_no_stts"))
    at, count = _table(window, *found, 8)
    runs = struct.iter_unpack(">II", window.take(at, count * 8))
    times: list[int] = []
    sample, clock, run = 1, 0, next(runs, None)
    for want in wanted:
        while run is not None and want >= sample + run[0]:
            sample += run[0]
            clock += run[0] * run[1]
            run = next(runs, None)
        if run is None:
            break
        times.append(clock + (want - sample) * run[1])
    return times


def _offsets(window: _Window, stbl: tuple[int, int], wanted: list[int]) -> list[int]:
    """Смещение нужных сэмплов в файле: ``stsc`` + ``stco``/``co64`` + ``stsz``.

    Тем же слиянием, и по той же причине. У YTS-релизов сэмпл в чанке один, поэтому
    смещение получается точным до байта; когда их несколько, ``stsz`` даёт размеры
    предшественников внутри чанка — и лежит он аккурат перед ``stco``, то есть читается
    по дороге и бесплатно.
    """
    plain = _find(window, *stbl, b"stco")
    chunks = plain or _find(window, *stbl, b"co64")
    counts = _find(window, *stbl, b"stsc")
    if chunks is None or counts is None:
        return []
    width = 4 if plain else 8
    at, count = _table(window, *chunks, width)
    where = struct.unpack(f">{count}{'I' if plain else 'Q'}", window.take(at, count * width))
    at, count = _table(window, *counts, 12)
    runs = list(struct.iter_unpack(">III", window.take(at, count * 12)))
    sizes = _sample_sizes(window, stbl)

    found: list[int] = []
    chunk, sample, step, index = 1, 1, 1, 0  # чанк, первый сэмпл в нём, сэмплов на чанк
    for want in wanted:
        while True:
            if index < len(runs) and chunk >= runs[index][0]:
                step = runs[index][1]
                index += 1
                continue
            if step <= 0:
                return found
            following = runs[index][0] if index < len(runs) else len(where) + 1
            if want < sample + step * (following - chunk):
                break
            sample += step * (following - chunk)
            chunk = following
        skip, inside = divmod(want - sample, step)
        chunk += skip
        sample += skip * step
        if chunk > len(where):
            break
        found.append(where[chunk - 1] + sum(sizes[sample - 1 : sample + inside - 1]))
    return found


def _sample_sizes(window: _Window, stbl: tuple[int, int]) -> list[int]:
    """Размеры сэмплов из ``stsz``; общий размер на все — пустой список не нужен."""
    found = _find(window, *stbl, b"stsz")
    if found is None:
        return []
    _, at = _full(window, found[0])
    one, count = struct.unpack(">II", window.take(at, 8))
    if one:
        return [one] * count
    at += 8
    count = min(count, max(0, (found[1] - at) // 4))
    return list(struct.unpack(f">{count}I", window.take(at, count * 4)))


def _composition(window: _Window, stbl: tuple[int, int], wanted: list[int]) -> dict[int, int]:
    """Сдвиги ``ctts`` для нужных сэмплов; нет таблицы — B-кадров нет и сдвига тоже.

    ⚠️ Именно этот сдвиг превращает время декодирования в то, что показывает ffprobe и
    по чему режет сегментный муксер. У «Моаны 2» он равен ``elst`` и с ним сокращается —
    но полагаться на это нельзя: в первом же релизе с другим кодировщиком они разъедутся.
    """
    found = _find(window, *stbl, b"ctts")
    if found is None:
        return {}
    at, count = _table(window, *found, 8)
    runs = struct.iter_unpack(">Ii", window.take(at, count * 8))
    ahead: dict[int, int] = {}
    sample, run = 1, next(runs, None)
    for want in wanted:
        while run is not None and want >= sample + run[0]:
            sample += run[0]
            run = next(runs, None)
        if run is None:
            break
        ahead[want] = run[1]
    return ahead
