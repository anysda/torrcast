#!/usr/bin/env python3
"""Замер бюджета прогрева: сколько диска съедает вечер и что об этом думает предсказание.

Считается по снятым картам опорных кадров и паспортам ffprobe, лежащим в кэше состояния:
раздача не спрашивается, показ не поднимается. По каждому файлу берётся та же сетка, что
построил бы показ (:func:`torrcast.stream.grid_for`), и тот же предсказатель веса куска -
поэтому число «сколько лягет на диск» тут не оценка на глаз, а расчёт показа.

Рядом печатается ``запрос`` - то, на что прогрев просит места у бюджета перед заходом
(:meth:`torrcast.warm.Warmer._forecast`): зовётся сам предсказатель, а не переписанная
тут арифметика, поэтому расхождение «запроса» с «копией» - это и есть ошибка прогрева,
а не ошибка щупа.

    python scripts/warmbudget.py --keys /var/lib/torrcast/keys --probe /var/lib/torrcast/probe

Инструмент разработчика: в устанавливаемый пакет не входит.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.stream import (
    AUDIO_MBIT,
    MAX_SEGMENT_BYTES,
    TS_OVERHEAD,
    Grid,
    _extra_mbit,
    _read_keys,
    _weigher,
)
from torrcast.warm import WARM_BUDGET, Vault, Warmer


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", required=True, help="каталог снятых карт опорных кадров")
    ap.add_argument("--probe", required=True, help="каталог паспортов ffprobe")
    ap.add_argument("--step", type=float, default=10.0, help="шаг сетки, секунды")
    ap.add_argument("--ceiling", type=float, default=9.0, help="потолок перекодирования, Мбит/с")
    ap.add_argument("--cap", type=int, default=MAX_SEGMENT_BYTES, help="потолок куска, байты")
    ap.add_argument("--budget", type=float, default=WARM_BUDGET / 1e9, help="бюджет прогрева, ГБ")
    args = ap.parse_args()

    rows = []
    for path in sorted(Path(args.keys).glob("*.json")):
        keys = _read_keys(path)
        card = Path(args.probe) / path.name
        if keys is None or len(keys.offset) != len(keys.at) or len(keys.at) < 3:
            continue
        try:
            media = json.loads(card.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        duration = float(media.get("duration") or keys.duration)
        video_mbit = float(media.get("video_bps") or 0.0) / 1e6
        if duration <= 0 or video_mbit <= 0:
            continue  # паспорт молчит о битрейте - считать нечего, гадать не будем
        delivered = (video_mbit + AUDIO_MBIT) * TS_OVERHEAD
        extra = _extra_mbit(keys, delivered)
        grid = Grid.on_keyframes(
            keys.at,
            duration,
            args.step,
            sizes=keys.offset,
            extra_mbit=extra,
            ceiling_mbit=args.ceiling,
            cap=args.cap,
        )
        # Два веса на один и тот же кусок. Копия - то, что прогрев кладёт на диск сразу
        # и чем занимает бюджет всё время показа; перекод - то, во что тяжёлые места
        # приводятся поздним заходом (:meth:`torrcast.warm.Warmer._spots_left`).
        copy = _weigher(keys.at, keys.offset, extra, 0.0)
        weigh = _weigher(keys.at, keys.offset, extra, args.ceiling)
        sizes = [copy(grid.start(k), grid.end(k)) for k in range(grid.count)]
        thin = [weigh(grid.start(k), grid.end(k)) for k in range(grid.count)]
        # Запрос - то, что прогрев просит у бюджета перед заходом на весь фильм
        # копией. Зовём сам предсказатель, а не его пересказ: щуп обязан мерять бой.
        warmer = Warmer(
            source="нет", audio=0, grid=grid, vault=Vault(root=Path("/nonexistent"), key="з")
        )
        rows.append(
            {
                "name": path.stem,
                "height": int(media.get("height") or 0),
                "hours": duration / 3600,
                "mbit": delivered,
                "pieces": grid.count,
                "real": sum(sizes),
                "thin": sum(thin),
                "ask": warmer._forecast(0, grid.count - 1),
                "heavy": sum(1 for s in sizes if s > args.cap),
            }
        )

    if not rows:
        print("считать нечего: карт с паспортом и битрейтом не нашлось")
        return 1
    budget = args.budget * 1e9
    print(f"файлов с картой и паспортом: {len(rows)}; бюджет {args.budget:g} ГБ")
    print("высота  часы  Мбит/с  кусков  копией_ГБ  после_ГБ  запрос_ГБ  тяжелее_потолка")
    for row in sorted(rows, key=lambda r: -r["real"])[:15]:
        print(
            f"{row['height']:6d}  {row['hours']:4.2f}  {row['mbit']:6.2f}  {row['pieces']:6d}  "
            f"{row['real'] / 1e9:9.2f}  {row['thin'] / 1e9:8.2f}  {row['ask'] / 1e9:9.2f}  "
            f"{row['heavy'] * 100 / row['pieces']:13.0f} %"
        )
    films = [r for r in rows if r["height"] >= 1000 and r["hours"] >= 1.2]
    parts = [r for r in rows if r["hours"] <= 0.6]
    if films:
        real = [r["real"] for r in films]
        ask = [r["ask"] for r in films]
        print(
            f"\n1080p длиннее 1.2 ч: {len(films)} шт; ляжет "
            f"{min(real) / 1e9:.1f}-{max(real) / 1e9:.1f} ГБ (медиана "
            f"{statistics.median(real) / 1e9:.1f}); запрос "
            f"{min(ask) / 1e9:.1f}-{max(ask) / 1e9:.1f} ГБ (медиана "
            f"{statistics.median(ask) / 1e9:.1f})"
        )
        print(
            f"доля бюджета: копией {statistics.median(real) / budget * 100:.0f} %, "
            f"по запросу {statistics.median(ask) / budget * 100:.0f} %"
        )
        heavy = [r["heavy"] * 100 / r["pieces"] for r in films]
        print(
            f"кусков тяжелее потолка копией: {min(heavy):.0f}-{max(heavy):.0f} %, "
            f"медиана {statistics.median(heavy):.0f} %"
        )
    if parts:
        short = [r["real"] for r in parts]
        print(
            f"короче 0.6 ч (серия): {len(parts)} шт; копией {min(short) / 1e9:.1f}-"
            f"{max(short) / 1e9:.1f} ГБ (медиана {statistics.median(short) / 1e9:.1f})"
        )
    if films and parts:
        pair = statistics.median(real) + statistics.median([r["real"] for r in parts])
        asked = statistics.median(ask) + statistics.median([r["ask"] for r in parts])
        print(
            f"обычный вечер (фильм + серия): копией {pair / 1e9:.1f} ГБ, "
            f"по запросу {asked / 1e9:.1f} ГБ при бюджете {args.budget:g} ГБ"
        )
        worst = max(real) + max(r["real"] for r in parts)
        worst_ask = max(ask) + max(r["ask"] for r in parts)
        print(
            f"худший фильм + серия: по факту {worst / 1e9:.1f} ГБ, "
            f"по запросу {worst_ask / 1e9:.1f} ГБ"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
