#!/usr/bin/env python3
"""Замер бюджета прогрева: сколько диска съедает вечер и что об этом думает предсказание.

Считается по снятым картам опорных кадров и паспортам ffprobe, лежащим в кэше состояния:
раздача не спрашивается, показ не поднимается. По каждому файлу берётся та же сетка, что
построил бы показ (:func:`torrcast.adapters.stream_pack.grid_for.grid_for`), и тот же предсказатель
веса куска - поэтому число «сколько лягет на диск» тут не оценка на глаз, а расчёт показа.

Рядом печатается ``запрос`` - то, на что прогрев просит места у бюджета перед заходом
(:meth:`torrcast.usecases.warm.Warmer._forecast`): зовётся сам предсказатель, а не переписанная
тут арифметика, поэтому расхождение «запроса» с «копией» - это и есть ошибка прогрева,
а не ошибка щупа.

    python scripts/warmbudget.py --keys /var/lib/torrcast/keys --probe /var/lib/torrcast/probe

Мерки приёмника (шаг сетки, порог перекода, потолок веса куска и во сколько ужимаем)
берутся из его профиля - тем же выбором, что и у показа; ``--profile`` называет профиль
руками, а каждый из ключей ниже перебивает своё число поимённо.

Инструмент разработчика: в устанавливаемый пакет не входит.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.stream_pack.extra_mbit import extra_mbit
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.read_keys import read_keys
from torrcast.adapters.stream_pack.weigher import weigher
from torrcast.domain.delivered_mbit import AUDIO_MBIT, TS_OVERHEAD
from torrcast.domain.warm_settings import WARM_BUDGET
from torrcast.usecases.warm.vault import Vault
from torrcast.usecases.warm.warmer import Warmer


@dataclass(frozen=True)
class _Row:
    """Один файл глазами замера: что по нему насчитали сетка, весы и предсказатель."""

    #: Имя карты без расширения - по нему строку сопоставляют с файлом.
    name: str
    height: int
    hours: float
    mbit: float
    pieces: int
    #: Байты, которые прогрев кладёт на диск копией всего фильма.
    real: float
    #: Байты после перекода тяжёлых мест поздним заходом.
    thin: float
    #: Байты, которые прогрев просит у бюджета перед заходом.
    ask: float
    #: Сколько кусков копией вышло тяжелее потолка веса.
    heavy: int
    #: Сколько кусков идут выше битрейта приёмника, то есть тяжелы ему сами по себе.
    over: int
    #: Сколько кусков поздний заход берёт в работу вообще: тяжёлые ИЛИ увесистые.
    touched: int


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", required=True, help="каталог снятых карт опорных кадров")
    ap.add_argument("--probe", required=True, help="каталог паспортов ffprobe")
    ap.add_argument("--step", type=float, help="шаг сетки, секунды")
    ap.add_argument("--ceiling", type=float, help="потолок перекодирования, Мбит/с")
    ap.add_argument(
        "--recode-at",
        type=float,
        help="битрейт приёмника, выше которого кусок перекодируется, Мбит/с",
    )
    ap.add_argument("--cap", type=int, help="потолок куска, байты")
    ap.add_argument("--budget", type=float, default=WARM_BUDGET / 1e9, help="бюджет прогрева, ГБ")
    add_profile_argument(ap)
    args = ap.parse_args()

    # Все четыре мерки - про ПРИЁМНИК, и берутся они его профилем, а не константой: у
    # смелого приёмника порог перекода втрое выше, и щуп с зашитой десяткой мерил бы
    # чужой вечер. Названное ключом сильнее профиля - как ``--profile`` сильнее паспорта.
    config, choice = choose_profile(load_config(), args.profile)
    step = args.step if args.step is not None else config.hls_segment
    ceiling = args.ceiling if args.ceiling is not None else config.recode_mbit
    recode_at = args.recode_at if args.recode_at is not None else config.recode_at_mbit
    cap = args.cap if args.cap is not None else choice.profile.max_segment_bytes

    rows: list[_Row] = []
    for path in sorted(Path(args.keys).glob("*.json")):
        keys = read_keys(path)
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
        extra = extra_mbit(keys, delivered)
        grid = Grid.on_keyframes(
            keys.at,
            duration,
            step,
            sizes=keys.offset,
            extra_mbit=extra,
            ceiling_mbit=ceiling,
            cap=cap,
        )
        # Два веса на один и тот же кусок. Копия - то, что прогрев кладёт на диск сразу
        # и чем занимает бюджет всё время показа; перекод - то, во что тяжёлые места
        # приводятся поздним заходом (:meth:`torrcast.usecases.warm.Warmer._spots_left`).
        copy = weigher(keys.at, keys.offset, extra, 0.0)
        weigh = weigher(keys.at, keys.offset, extra, ceiling)
        sizes = [copy(grid.start(k), grid.end(k)) for k in range(grid.count)]
        spans = [max(0.0, grid.end(k) - grid.start(k)) for k in range(grid.count)]
        # Битрейт куска - тот же, которым меряет отбор тяжёлых мест: байты копии на длину.
        mbits = [sizes[k] * 8 / spans[k] / 1e6 if spans[k] > 0 else 0.0 for k in range(grid.count)]
        # Поздний заход берёт кусок по ДВУМ меркам сразу, и они не совпадают: битрейт выше
        # приёмника ИЛИ копия тяжелее потолка веса. Мерки разведены по приёмникам порознь:
        # битрейт у смелого приёмника втрое выше, а потолок веса у обоих один и тот же,
        # поэтому увесистые куски перекодируются даже там, где по битрейту никто не тяжёл.
        # Кусок, который заход не берёт, остаётся копией навсегда - его вес и есть ответ.
        taken = [mbits[k] >= recode_at or sizes[k] > cap for k in range(grid.count)]
        thin = [
            weigh(grid.start(k), grid.end(k)) if taken[k] else sizes[k] for k in range(grid.count)
        ]
        # Запрос - то, что прогрев просит у бюджета перед заходом на весь фильм
        # копией. Зовём сам предсказатель, а не его пересказ: щуп обязан мерять бой.
        warmer = Warmer(
            source="нет", audio=0, grid=grid, vault=Vault(root=Path("/nonexistent"), key="з")
        )
        rows.append(
            _Row(
                name=path.stem,
                height=int(media.get("height") or 0),
                hours=duration / 3600,
                mbit=delivered,
                pieces=grid.count,
                real=sum(sizes),
                thin=sum(thin),
                ask=warmer._forecast(0, grid.count - 1),
                heavy=sum(1 for s in sizes if s > cap),
                over=sum(1 for m in mbits if m >= recode_at),
                touched=sum(1 for t in taken if t),
            )
        )

    if not rows:
        print("считать нечего: карт с паспортом и битрейтом не нашлось")
        return 1
    budget = args.budget * 1e9
    print(
        f"файлов с картой и паспортом: {len(rows)}; бюджет {args.budget:g} ГБ; "
        f"приёмник: перекод выше {recode_at:g} Мбит/с, потолок куска "
        f"{cap / 1e6:g} МБ, ужимаем до {ceiling:g} Мбит/с"
    )
    print(
        "высота  часы  Мбит/с  кусков  копией_ГБ  после_ГБ  запрос_ГБ  "
        "тяжелее_потолка  выше_битрейта  взято_заходом"
    )
    for row in sorted(rows, key=lambda r: -r.real)[:15]:
        print(
            f"{row.height:6d}  {row.hours:4.2f}  {row.mbit:6.2f}  {row.pieces:6d}  "
            f"{row.real / 1e9:9.2f}  {row.thin / 1e9:8.2f}  {row.ask / 1e9:9.2f}  "
            f"{row.heavy * 100 / row.pieces:13.0f} %  "
            f"{row.over * 100 / row.pieces:11.0f} %  "
            f"{row.touched * 100 / row.pieces:11.0f} %"
        )
    films = [r for r in rows if r.height >= 1000 and r.hours >= 1.2]
    parts = [r for r in rows if r.hours <= 0.6]
    if films:
        real = [r.real for r in films]
        ask = [r.ask for r in films]
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
        heavy = [r.heavy * 100 / r.pieces for r in films]
        print(
            f"кусков тяжелее потолка копией: {min(heavy):.0f}-{max(heavy):.0f} %, "
            f"медиана {statistics.median(heavy):.0f} %"
        )
        over = [r.over * 100 / r.pieces for r in films]
        print(
            f"кусков выше битрейта приёмника: {min(over):.0f}-{max(over):.0f} %, "
            f"медиана {statistics.median(over):.0f} %"
        )
        # Имя своё, не ``taken``: там выше - флаги по кускам одного фильма, тут проценты
        # по фильмам. Пока пороги приходили из ``argparse``, обе строки были нетипизованы,
        # и подмена смысла под одним именем не читалась ни глазом, ни проверкой типов.
        touched = [r.touched * 100 / r.pieces for r in films]
        print(
            f"кусков берёт поздний заход: {min(touched):.0f}-{max(touched):.0f} %, "
            f"медиана {statistics.median(touched):.0f} %"
        )
        # Место возвращается ровно на разнице «копия минус то, что осталось после захода».
        # Заход не трогал ни одного куска - разница ноль, и место не вернётся никогда.
        back = [r.real - r.thin for r in films]
        rest = [r.thin for r in films]
        print(
            f"заход возвращает: {min(back) / 1e9:.1f}-{max(back) / 1e9:.1f} ГБ "
            f"(медиана {statistics.median(back) / 1e9:.1f}); остаётся лежать "
            f"{min(rest) / 1e9:.1f}-{max(rest) / 1e9:.1f} ГБ "
            f"(медиана {statistics.median(rest) / 1e9:.1f})"
        )
        print(
            f"фильмов, не влезающих в бюджет в одиночку: "
            f"{sum(1 for r in films if r.real > budget)} из {len(films)} копией, "
            f"{sum(1 for r in films if r.thin > budget)} после захода"
        )
        # Второй фильм за вечер. Первый к этому времени уже прошёл поздний заход и лежит
        # ужатым, второй ложится копией: пик задаёт эта сумма, а не любая из них порознь.
        two = statistics.median(rest) + statistics.median(real)
        two_worst = max(rest) + max(real)
        print(
            f"два фильма подряд: медиана {two / 1e9:.1f} ГБ, худший "
            f"{two_worst / 1e9:.1f} ГБ при бюджете {args.budget:g} ГБ"
        )
    if parts:
        short = [r.real for r in parts]
        print(
            f"короче 0.6 ч (серия): {len(parts)} шт; копией {min(short) / 1e9:.1f}-"
            f"{max(short) / 1e9:.1f} ГБ (медиана {statistics.median(short) / 1e9:.1f})"
        )
    if films and parts:
        pair = statistics.median(real) + statistics.median([r.real for r in parts])
        asked = statistics.median(ask) + statistics.median([r.ask for r in parts])
        print(
            f"обычный вечер (фильм + серия): копией {pair / 1e9:.1f} ГБ, "
            f"по запросу {asked / 1e9:.1f} ГБ при бюджете {args.budget:g} ГБ"
        )
        worst = max(real) + max(r.real for r in parts)
        worst_ask = max(ask) + max(r.ask for r in parts)
        print(
            f"худший фильм + серия: по факту {worst / 1e9:.1f} ГБ, "
            f"по запросу {worst_ask / 1e9:.1f} ГБ"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
