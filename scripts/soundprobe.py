#!/usr/bin/env python3
"""Замер звука в готовых сегментах показа: громкость, пик, дорожка, расхождение с картинкой.

Инструмент разработчика: в устанавливаемый пакет не входит.

    python3 scripts/soundprobe.py /путь/до/сегментов/v3.ts v4.ts
    python3 scripts/soundprobe.py --dir /путь/до/каталога/сегментов --take 3

Пока звук описан словом («ужасно»), чинить нечего и доказывать нечего. Щуп переводит
слово в четыре числа на сегмент, ровно те, по которым слышимая разница и отличается от
послышавшейся:

* **интегральная громкость** ``I``, LUFS, фильтром ``ebur128`` - тот же прибор, которым
  меряют вещание. Мастеринг кино держится около -24...-18 LUFS; заметно ниже - зритель
  выкручивает громкость и вместе с речью поднимает шум;
* **истинный пик** ``TP``, dBTP, с ``peak=true``. Положительный пик - это клиппинг:
  сумма каналов не поместилась в шкалу и срезана, на слух - хрип на громком;
* **что за дорожка приехала**: кодек, число каналов, битрейт и язык из самого сегмента,
  а не из паспорта исходника. ``audio_index`` - НОМЕР потока, промах по нему даёт чужой
  язык при верном следе отбора;
* **расхождение звука с картинкой**: разница ``start_time`` звуковой и видеодорожки в
  миллисекундах. Видео уезжает копией, звук перекодируется
  (:func:`torrcast.adapters.ffmpeg.pack_command.pack_command`), и метки у них ставят
  разные ветки муксера.

Щуп ничего не чинит и ничего не решает: порога в нём нет, он печатает числа. Где резать -
решает сторож (``tests/adapters/ffmpeg/test_pack_audio_entry.py``), а не прибор.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

#: Хвост вывода ``ebur128``: итог печатается после строки ``Summary:`` и только там.
#: Построчные ``[Parsed_ebur128`` дают МГНОВЕННУЮ громкость, и брать их за итог - ровно
#: тот способ, которым щуп показывает -70 LUFS на тихой первой секунде.
_SUMMARY: re.Pattern[str] = re.compile(r"Summary:(.*)", re.S)
_FIELD: re.Pattern[str] = re.compile(r"^\s*(I|LRA|Peak):\s*(-?\d+\.?\d*)\s", re.M)


def _run(argv: list[str]) -> str:
    """Выполнить и вернуть весь вывод; ``ffmpeg`` пишет замер в поток ошибок."""
    done = subprocess.run(argv, capture_output=True, text=True, check=False)
    return done.stdout + done.stderr


def loudness(path: Path) -> dict[str, float | None]:
    """Интегральная громкость, разброс и истинный пик одного файла."""
    out = _run(
        ["ffmpeg", "-nostdin", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"]
    )
    tail = _SUMMARY.search(out)
    if tail is None:
        return {"lufs": None, "lra": None, "peak": None}
    found = dict(_FIELD.findall(tail.group(1)))
    return {
        "lufs": float(found["I"]) if "I" in found else None,
        "lra": float(found["LRA"]) if "LRA" in found else None,
        "peak": float(found["Peak"]) if "Peak" in found else None,
    }


def streams(path: Path) -> dict[str, object]:
    """Кодек, каналы, битрейт и язык дорожки плюс расхождение звука с картинкой."""
    out = _run(
        ["ffprobe", "-v", "error", "-of", "json", "-show_entries",
         "stream=codec_type,codec_name,channels,bit_rate,start_time:stream_tags=language",
         str(path)],
    )  # fmt: skip
    try:
        found: list[dict[str, Any]] = json.loads(out).get("streams", [])
    except json.JSONDecodeError:
        return {"codec": None, "channels": None, "bitrate": None, "language": None, "skew": None}
    empty: dict[str, Any] = {}
    audio = next((s for s in found if s.get("codec_type") == "audio"), empty)
    video = next((s for s in found if s.get("codec_type") == "video"), empty)
    skew = None
    if "start_time" in audio and "start_time" in video:
        skew = round((float(audio["start_time"]) - float(video["start_time"])) * 1000, 1)
    rate = audio.get("bit_rate")
    tags: dict[str, Any] = audio.get("tags") or {}
    return {
        "codec": audio.get("codec_name"),
        "channels": audio.get("channels"),
        "bitrate": round(int(rate) / 1000) if rate else None,
        "language": tags.get("language"),
        "skew": skew,
    }


def measure(path: Path) -> dict[str, object]:
    """Все числа по одному сегменту."""
    row: dict[str, object] = {"segment": path.name}
    row.update(streams(path))
    row.update(loudness(path))
    return row


def segments(where: Path, take: int) -> list[Path]:
    """Сегменты каталога по возрастанию номера; ``init.mp4`` и списки резов не в счёт."""
    found = [p for p in where.rglob("v*") if p.suffix in (".ts", ".m4s", ".mp4")]
    found.sort(key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    return found[:take] if take > 0 else found


def _column(rows: list[dict[str, object]], name: str) -> int:
    """Ширина колонки по самому длинному значению, но не уже заголовка."""
    return max([len(name)] + [len(str(row.get(name))) for row in rows])


def table(rows: list[dict[str, object]]) -> str:
    """Числа таблицей: одна строка на сегмент, заголовки - имена полей."""
    if not rows:
        return "сегментов не найдено"
    names = list(rows[0])
    width = {name: _column(rows, name) for name in names}
    lines = ["  ".join(name.ljust(width[name]) for name in names)]
    lines.append("  ".join("-" * width[name] for name in names))
    for row in rows:
        lines.append("  ".join(str(row.get(name)).ljust(width[name]) for name in names))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Померить названные сегменты и напечатать таблицу или JSON."""
    parser = argparse.ArgumentParser(description="замер звука в сегментах показа")
    parser.add_argument("paths", nargs="*", type=Path, help="сегменты")
    parser.add_argument("--dir", type=Path, default=None, help="каталог сегментов")
    parser.add_argument("--take", type=int, default=3, help="сколько первых брать из каталога")
    parser.add_argument("--json", action="store_true", help="выдать JSON вместо таблицы")
    args = parser.parse_args(argv)
    paths = list(args.paths)
    if args.dir is not None:
        paths += segments(args.dir, args.take)
    if not paths:
        parser.error("назовите сегменты или --dir")
    rows = [measure(path) for path in paths]
    print(json.dumps(rows, ensure_ascii=False, indent=2) if args.json else table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
