#!/usr/bin/env python3
"""Сверяет ответ пробного прогона с настоящим местом посадки там, где меток в файле нет.

Пробный прогон показа (:func:`torrcast.adapters.stream_pack.pack_start.pack_start`)
меряет место посадки одним способом: копирует один кадр в mpegts и читает метку первого
пакета. У .avi меток нет вовсе - демультиплексор отдаёт пакеты с одним лишь ``dts``, а при
B-кадрах и ``pts`` первого пакета пуст, - и mpegts отказывается такой поток принимать
(``first pts and dts value must be set``). Прогон кончается ничем, ответом становится сама
запрошенная граница, и отличить «встали ровно на границе» от «не измерили ничего» по
ответу нельзя.

Щуп меряет то же место вторым способом и кладёт оба ответа рядом. Второй способ - тот же
самый прогон с той же перемоткой, которому добавлен ``-bsf:v setts=pts=DTS``: метка
берётся из ``dts``, и мультиплексору становится что писать. Перемотка при этом не
трогается ни на шаг, то есть меряется ровно та посадка, которая была бы у показа.

Поверка способа. На контейнере, где боевой прогон работает, щуп обязан назвать РОВНО тот
``dts``, который печатает сам боевой прогон, - и это сверяется на каждой границе
(``поверено``/``поверка разошлась`` в итоге). Там, где у потока нет B-кадров, ``pts``
равен ``dts``, и тогда щуп обязан совпасть с ответом продукта знак в знак.

    python3 scripts/pilotcheck.py URL --duration 300
    python3 scripts/pilotcheck.py URL --duration 7200 --step 10

На stdout пишется JSONL: строка на границу, затем итог. Щуп ничего не знает о каталоге,
раздаче и стенде; URL и длительность задаёт измеряющий.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# Щуп зовёт продукт и обязан звать СВОЙ: editable-установка венва смотрит на соседний
# клон, и без этой строки замер снимался бы кодом, который правят в чужой работе.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from seekgaps import boundaries, film_begins

from torrcast.adapters.stream_pack.pack_start import pack_start
from torrcast.adapters.stream_pack.run_refusal import run_refusal
from torrcast.domain.hls_settings import HLS_SEGMENT_SECONDS, SPLIT_SLACK

#: Один тик часов mpegts, секунды. Обе метки поверки пишутся одним и тем же
#: мультиплексором и квантуются его сеткой 90 кГц; допуск поверки - ровно этот тик, а не
#: свободное число: шире - и поверка перестала бы ловить разъезд на целый кадр.
MPEGTS_TICK: Final = 1.0 / 90000.0

#: Ответ продукта совпал с измеренным местом: пробный прогон сказал правду.
AGREED = "сошлось"
#: Прогон не дал ни одного пакета, и ответом стала сама граница. Место не измерено ничем.
VERBATIM = "граница дословно"
#: Прогон ответил, но не тем числом, которое намерил второй способ.
APART = "разошлось"


@dataclass(frozen=True, slots=True)
class Row:
    """Одна граница: что ответил продукт, что намерено на самом деле и сошлось ли."""

    at: float
    told: float
    stood: float | None
    plain: float | None
    error: str
    kind: str


def first_packet(url: str, at: float, timeout: float, *, patched: bool) -> tuple[str, str, str]:
    """Метки первого пакета копирующего прогона: ``pts``, ``dts`` и строка отказа.

    Команда до последнего довода та же, которой место посадки меряет показ. ``patched``
    добавляет ``-bsf:v setts=pts=DTS``: битстримный фильтр ставит пустому ``pts`` значение
    ``dts`` уже ПОСЛЕ перемотки и выбора пакета, поэтому место посадки он не двигает, а
    только даёт мультиплексору метку, без которой тот отказывается писать.
    """
    with tempfile.TemporaryDirectory(prefix="pilotcheck-") as tmp:
        first = Path(tmp) / "first.ts"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-copyts", "-ss", f"{at:.3f}",
            "-i", url, "-map", "0:v:0", "-c", "copy", "-frames:v", "1",
        ]  # fmt: skip
        if patched:
            command += ["-bsf:v", "setts=pts=DTS"]
        command += ["-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-y", str(first)]
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return "", "", str(exc)
        # 🔴 Код возврата тут не судья: mpegts умеет напечатать отказ и выйти НУЛЁМ, оставив
        # пустой файл. Признак удачи - прочитанный пакет, а признак беды - строка отказа.
        broke = run_refusal(done.stderr)
        try:
            found = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                 "packet=pts_time,dts_time", "-of", "csv=p=0", "-read_intervals", "%+#1",
                 str(first)],
                capture_output=True, text=True, timeout=timeout,
            )  # fmt: skip
        except (OSError, subprocess.SubprocessError) as exc:
            return "", "", broke or str(exc)
        head = found.stdout.strip().splitlines()
        if not head:
            return "", "", broke or f"первого пакета нет, код {done.returncode}"
        stamps = [*head[0].split(","), "", ""][:2]
        return stamps[0].strip(), stamps[1].strip(), broke


def _number(text: str) -> float | None:
    """Метка ffprobe числом; ``N/A`` и пустая строка - ``None``, а не ноль."""
    try:
        return float(text)
    except ValueError:
        return None


def check(url: str, at: float, timeout: float, begins: float) -> Row:
    """Одна граница: спросить продукт, намерить место вторым способом и свести ответы.

    Продукт спрашивается через :func:`pack_start` - тем же входом, которым его зовёт показ.
    Карты опорных кадров у .avi не бывает вовсе, и там этот вход и есть пробный прогон.
    """
    told = pack_start(url, at, timeout, None)
    _pts, plain_dts, broke = first_packet(url, at, timeout, patched=False)
    patched_pts, _dts, patched_broke = first_packet(url, at, timeout, patched=True)
    stood = _number(patched_pts)
    if stood is not None:
        stood -= begins
    plain = _number(plain_dts)
    if plain is not None:
        plain -= begins
    error = broke or patched_broke
    if stood is None:
        kind = APART
    elif abs(told - stood) <= SPLIT_SLACK:
        kind = AGREED
    elif abs(told - at) <= SPLIT_SLACK:
        kind = VERBATIM
    else:
        kind = APART
    return Row(at, told, stood, plain, error, kind)


def summary(rows: list[Row], begins: float) -> dict[str, object]:
    """Итог по одному файлу: где продукт сказал правду, где промолчал границей и на сколько.

    ``поверка`` - главное число этого щупа, а не сноска: на каждой границе, где боевой
    прогон дал пакет, второй способ обязан назвать РОВНО его ``dts``. Разошлась поверка -
    верить остальным числам нечему, и они читаются как мусор.
    """
    measured = [row for row in rows if row.stood is not None]
    proven = [row for row in measured if row.plain is not None]
    same = [row for row in proven if abs((row.stood or 0.0) - (row.plain or 0.0)) <= MPEGTS_TICK]
    gaps = [abs(row.told - (row.stood or 0.0)) for row in measured]
    kinds = {name: sum(row.kind == name for row in rows) for name in (AGREED, VERBATIM, APART)}
    return {
        "итог": True,
        "границ": len(rows),
        "измерено вторым способом": len(measured),
        "боевой прогон дал пакет": len(proven),
        "поверено": len(same),
        "поверка разошлась": len(proven) - len(same),
        AGREED: kinds[AGREED],
        VERBATIM: kinds[VERBATIM],
        APART: kinds[APART],
        "наибольшее расхождение": round(max(gaps, default=0.0), 6),
        "среднее расхождение": round(sum(gaps) / len(gaps), 6) if gaps else 0.0,
        "начало видео": round(begins, 3),
        "отказ прогона": next((row.error for row in rows if row.error), ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Сверка пробного прогона с настоящей посадкой")
    parser.add_argument("url")
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--step", type=float, default=HLS_SEGMENT_SECONDS)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    if args.duration <= 0 or args.step <= 0 or args.timeout <= 0:
        parser.error("длительность, шаг и таймаут положительны")
    begins = film_begins(args.url, args.timeout)
    rows = []
    for at in boundaries(args.duration, args.step):
        row = check(args.url, at, args.timeout, begins)
        rows.append(row)
        print(
            json.dumps(
                {
                    "граница": row.at,
                    "ответ продукта": round(row.told, 6),
                    "намерено": None if row.stood is None else round(row.stood, 6),
                    "dts боевого прогона": None if row.plain is None else round(row.plain, 6),
                    "расхождение": None if row.stood is None else round(row.told - row.stood, 6),
                    "исход": row.kind,
                    "отказ": row.error,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    print(json.dumps(summary(rows, begins), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
