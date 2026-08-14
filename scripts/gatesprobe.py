#!/usr/bin/env python3
"""Щуп ворот отбора: что пропускает порядок очереди и весовые ступени (офлайн).

Инструмент разработчика: в устанавливаемый пакет не входит. Живых служб не нужно:
пулы - сохранённые выдачи индексеров (формат :mod:`poolreplay`), разбор делает ровно
боевой тракт (:func:`poolreplay.replay`).

    python scripts/gatesprobe.py pools.jsonl

Меряет три класса, у каждого свой счёт и свой список случаев:

* **SD наверху** - верх очереди отбора, про разрешение которого имя молчит, при живом
  названном HD ниже. После того как MPEG-4 перестал быть отказом показа, такой верх
  СЫГРАЕТ то, что внутри, и единственная защита - разворот по ffprobe
  (:func:`torrcast.cli.understated`), а не ворота. Контрольный счёт «датированный верх
  при живом HD ниже» обязан быть нулём: его держит ступень
  :func:`torrcast.cli.is_dated`.
* **«не знаю» против «мало»** - сериальные раздачи, чьё имя серий не считает
  (:func:`torrcast.cli.bitrate_of` отдаёт ``None``): сколько их в очередях и верхах, и
  где ворота читают это молчание как вес.
* **тяжёлые приложения** - раздачи с меткой приложения в имени, которые ворота
  пропускают из-за веса (:func:`torrcast.cli.is_extra` судит имя ВМЕСТЕ с битрейтом):
  сколько их, насколько они тяжелы и как высоко стоят.

Последним блоком - гейт TC-290: сколько картин меню потеряли бы последнего живого
кандидата, если бы приложения выкидывались по одному имени. Это число обязано быть
нулём у любой правки этих ворот.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import poolreplay
from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile

from torrcast.cli import HD_HEIGHT, Args, _Plan, bitrate_of, is_dated, is_extra
from torrcast.parse import _EXTRAS_RE, Release
from torrcast.state import load_config


def live_hd_below(plan: _Plan, queue: list[int]) -> list[int]:
    """Живые названные HD ниже верха очереди - те, кого позвал бы разворот по ffprobe.

    Датированные не считаются: ступень :func:`is_dated` уже уложила их под верх, и
    стоять ниже него по сидам - их законное место, а не провал сетки.
    """
    return [
        n
        for n in queue[1:]
        if plan.ranked[n - 1].height >= HD_HEIGHT
        and plan.ranked[n - 1].seeders > 0
        and not is_dated(plan.ranked[n - 1], plan.runtime)
    ]


def mark_of(release: Release) -> str:
    """Какая метка приложения сработала в имени; пусто - метки нет (контроль)."""
    found = _EXTRAS_RE.search(release._untitled)
    return found.group(0) if found else ""


def weight_unknown(release: Release) -> bool:
    """Прикидка битрейта молчит: сериал, чьё имя серий не считает."""
    return release.kind == "tv" and not release.episode_count


#: Метки приложения, которые не бывают у законной картины в зоне пометок:
#: «Дополнительные материалы», «бонус-диск». Остальные («бонус», «за кадром»,
#: «интервью») бывают частью собственного имени раздачи-картины.
_UNAMBIGUOUS_RE = re.compile(
    r"доп(?:олнительн\w*|\.)?\s*материал\w*|бонус\w*[\s._-]*диск\w*|bonus[\s._-]*disc",
    re.IGNORECASE,
)


def unambiguous_extra(release: Release) -> bool:
    """Имя несёт однозначную метку приложения (в зоне пометок, не в имени картины)."""
    return bool(_UNAMBIGUOUS_RE.search(release._untitled))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="щуп ворот отбора по сохранённым выдачам")
    ap.add_argument("pools", type=Path, help="pools.jsonl со снятыми выдачами индексеров")
    add_profile_argument(ap)
    args = ap.parse_args(argv)

    config, choice = choose_profile(load_config(), args.profile)
    items = []
    for line in args.pools.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        batches = poolreplay.batches_of(record)
        items.append(
            poolreplay.replay(str(record.get("query", "")), batches, config, choice.profile)
        )

    plans = [plan for item in items for plan in item.plans]

    # --- SD наверху -----------------------------------------------------------
    dated_top_hd_below: list[str] = []
    silent_top_hd_below: list[str] = []
    tops = {"dated": 0, "named": 0, "silent": 0}
    for plan in plans:
        queue = plan.candidates(Args(query=plan.picture.title.split()))
        if not queue:
            continue
        top = plan.ranked[queue[0] - 1]
        kind = "dated" if is_dated(top, plan.runtime) else ("named" if top.height else "silent")
        tops[kind] += 1
        below = live_hd_below(plan, queue)
        if not below:
            continue
        row = (
            f"{plan.picture.title}: верх «{top.raw_name[:70]}» "
            f"({top.seeders} сид, {top.size / 1024**3:.1f} ГБ, "
            f"{top.codec or '-'}, {top.source or '-'}), живой HD ниже: {below}"
        )
        if kind == "silent":
            row += "\n    ниже: " + "; ".join(
                f"№{n} {plan.ranked[n - 1].quality} {plan.ranked[n - 1].seeders}с "
                f"{plan.ranked[n - 1].codec or '-'}"
                for n in below[:4]
            )
        (
            dated_top_hd_below
            if kind == "dated"
            else silent_top_hd_below
            if kind == "silent"
            else []
        ).append(row)

    print("=== SD наверху ===")
    print(f"картин с очередью: {sum(tops.values())}, верхи: {tops}")
    print(f"датированный верх при живом HD ниже (обязан быть 0): {len(dated_top_hd_below)}")
    for row in dated_top_hd_below:
        print(f"  {row}")
    print(f"молчаливый верх при живом HD ниже (судит только ffprobe): {len(silent_top_hd_below)}")
    for row in silent_top_hd_below:
        print(f"  {row}")

    # --- «не знаю» против «мало» ----------------------------------------------
    unknown_total = unknown_queued = unknown_top = 0
    unknown_extras_dropped: list[str] = []
    for plan in plans:
        queue = plan.candidates(Args(query=plan.picture.title.split()))
        members = set(queue)
        for n, release in enumerate(plan.ranked, start=1):
            if not weight_unknown(release):
                continue
            unknown_total += 1
            if n in members:
                unknown_queued += 1
                if n == queue[0]:
                    unknown_top += 1
            if release.extras and is_extra(release, plan.runtime):
                unknown_extras_dropped.append(
                    f"{plan.picture.title}: «{release.raw_name[:70]}» "
                    f"({release.seeders} сид, {release.size / 1024**3:.1f} ГБ)"
                )

    print("\n=== «не знаю» против «мало» ===")
    print(
        f"сериальных раздач без счёта серий в пулах меню: {unknown_total}, "
        f"в очередях: {unknown_queued}, верхами очереди: {unknown_top}"
    )
    print(f"из них приложения, выкинутые воротами по нулевому весу: {len(unknown_extras_dropped)}")
    for row in unknown_extras_dropped:
        print(f"  {row}")

    # --- тяжёлые приложения ----------------------------------------------------
    heavy_extras: list[str] = []
    extras_named = 0
    for plan in plans:
        queue = plan.candidates(Args(query=plan.picture.title.split()))
        positions = {n: place for place, n in enumerate(queue, start=1)}
        for n, release in enumerate(plan.ranked, start=1):
            if not release.extras or is_extra(release, plan.runtime):
                extras_named += bool(release.extras)
                continue
            extras_named += 1
            mbit = bitrate_of(release, plan.runtime)
            shown = f"~{mbit:.1f} Мбит/с" if mbit is not None else "вес неизвестен"
            heavy_extras.append(
                f"{plan.picture.title}: «{release.raw_name[:70]}» "
                f"({release.seeders} сид, {release.size / 1024**3:.1f} ГБ, "
                f"{shown}, метка «{mark_of(release)}», "
                f"место в очереди: {positions.get(n, 'отсеян')})"
            )

    print("\n=== тяжёлые приложения ===")
    print(f"раздач с меткой приложения в пулах меню: {extras_named}")
    print(f"проходят ворота по весу (тяжёлые): {len(heavy_extras)}")
    for row in heavy_extras:
        print(f"  {row}")

    # --- гейт TC-290 -----------------------------------------------------------
    # Верх очереди (ranked[0]) ворота не трогают никогда (:meth:`_Plan.candidates`),
    # поэтому потеря - это очередь, в которой не осталось НИ ОДНОГО живого. Два
    # варианта отсева приложений: по ЛЮБОЙ метке и только по однозначной
    # («дополнительные материалы», «бонус-диск») с сохранением верха.
    lost_any = lost_unamb = 0
    lost_rows: list[str] = []
    for plan in plans:
        queue = plan.candidates(Args(query=plan.picture.title.split()))
        live_now = [n for n in queue if plan.ranked[n - 1].seeders > 0]
        if not live_now:
            continue
        if not [n for n in live_now if not plan.ranked[n - 1].extras]:
            lost_any += 1
        kept = [queue[0]] + [
            n for n in live_now if n != queue[0] and not unambiguous_extra(plan.ranked[n - 1])
        ]
        if not [n for n in kept if plan.ranked[n - 1].seeders > 0]:
            lost_unamb += 1
            names = "; ".join(
                f"«{plan.ranked[n - 1].raw_name[:60]}» ({mark_of(plan.ranked[n - 1])})"
                for n in live_now
            )
            lost_rows.append(f"  {plan.picture.title}: живые только приложения: {names}")

    print("\n=== гейт TC-290 ===")
    print(f"отсев по ЛЮБОЙ метке, включая верх - потеряли бы всех живых: {lost_any}")
    print(f"отсев по однозначной метке с сохранением верха - потеряли бы: {lost_unamb}")
    for row in lost_rows:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
