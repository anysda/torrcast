#!/usr/bin/env python3
"""Цель прогрева против ступени взятия: греем ли ту картину, которую включит Enter.

Инструмент разработчика: в устанавливаемый пакет не входит. Сети не трогает вовсе -
корпус сохранённых выдач прогоняется тем же офлайновым трактом, что и :mod:`poolreplay`.

    python scripts/warmseam.py /home/claude/homelab/tmp/tc770/pools-both.jsonl

Меряется ровно шов TC-829. Под меню греется голова :func:`warm_order`
(:data:`~torrcast.domain.prewarm_settings.PREWARM` картин плюс запасной релиз у первой),
а картину включает :func:`_pick_plan`. Это две РАЗНЫЕ ступени, и щуп спрашивает обе:

* цель прогрева - голова :func:`warm_order`, та картина, которой достаётся запасной релиз;
* ступень взятия - что вернёт настоящий :func:`_pick_plan`, когда человек жмёт Enter.

🔴 Ступень взятия тут не пересказана, а ВЫЗВАНА: подделан ровно ввод-вывод пульта
(:class:`tests.usecases.choice.world.Outside`), а правила отбора, живости и стражи
работают боевые. Пересказ ступени в щупе означал бы, что щуп и код расходятся тем же
швом, который щуп ищет.

⚠️ Число расхождений - **оценка снизу**. Офлайн-переигровка ходит только первый круг
поиска, а боевой путь добирает вторым (:func:`beyond_first_circle` в poolreplay): часть
запросов на живом пути получает в меню больше картин, и расхождений там может быть
больше, но не меньше.

Цена в секундах - модель по ЗАМЕРЕННЫМ числам репы, а не отдельный замер:

* :data:`COLD_RISE` - подъём одной раздачи с нуля, 6-7 с чистого ожидания DHT и ffprobe
  (:data:`~torrcast.domain.prewarm_settings.PREWARM_SPARE`, замер TC-120);
* :data:`~torrcast.domain.pick_settings.SWARM_GRACE` - отсрочка молчащего роя: у картины,
  чей верх очереди ниже :data:`~torrcast.domain.rank_settings.ALIVE_SEEDERS`, подъём
  сперва упирается в эту отсрочку и только потом уходит по очереди дальше.

Поэтому расхождение на картине с живым роем стоит зрителю единиц секунд, а на картине с
молчащим роем - десятков: это и есть та разница, ради которой цена считается в секундах,
а не в числе запросов.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from poolreplay import batches_of, capped_of, replay
from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile

from tests.usecases.choice.world import Outside, outside
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.args import Args
from torrcast.domain.pick_settings import SWARM_GRACE
from torrcast.domain.prewarm_settings import PREWARM
from torrcast.domain.rank_settings import ALIVE_SEEDERS
from torrcast.runtime.wire import wire
from torrcast.usecases.choice._pick_plan import _pick_plan
from torrcast.usecases.choice.enter_take import enter_take
from torrcast.usecases.choice.liveliness import liveliness
from torrcast.usecases.choice.warm_order import warm_order

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan

#: Подъём одной раздачи с нуля, с: середина замеренных 6-7 с ожидания DHT и ffprobe
#: (:data:`~torrcast.domain.prewarm_settings.PREWARM_SPARE`). Ровно эти секунды прогрев
#: под меню и переносит в паузу, пока человек читает список.
COLD_RISE = 6.5


@dataclass(slots=True)
class Seam:
    """Что сказали обе ступени по одному запросу корпуса."""

    query: str
    #: Картин в меню: расхождению есть где случиться только при двух и больше.
    plans: int
    #: Год и имя картины, которую греет прогрев первой; "" - греть нечего.
    warmed: str = ""
    #: Год и имя картины, которую включит Enter; "" - взятия нет (отказ или нет дефолта).
    taken: str = ""
    #: Почему взятия нет: отказ ступени или вопрос без дефолта.
    refused: str = ""
    #: Попала ли взятая картина хотя бы в прогретую голову PREWARM картин.
    warm_head: bool = False
    #: Сиды лучшей годной раздачи взятой картины (:func:`liveliness`).
    alive: int = 0

    @property
    def diverged(self) -> bool:
        """Разошлись ли цель прогрева и ступень взятия."""
        return bool(self.taken) and self.taken != self.warmed

    @property
    def cost(self) -> float:
        """Во сколько секунд расхождение обходится зрителю.

        Взятая картина не попала в прогретую голову вовсе - зритель платит подъём с нуля
        целиком. Попала, но не первой - потерян ровно запасной релиз
        (:data:`~torrcast.domain.prewarm_settings.PREWARM_SPARE`), и платится он только на
        бракованном верхе; в общую сумму такое не кладётся, оно считается отдельно.
        """
        if not self.diverged or self.warm_head:
            return 0.0
        return COLD_RISE + (0.0 if self.alive >= ALIVE_SEEDERS else SWARM_GRACE)


def named(plan: Plan) -> str:
    """Имя картины с годом - как её называет меню."""
    return f"{plan.picture.title} ({plan.picture.year})"


def seam_of(query: str, plans: list[Plan]) -> Seam:
    """Спросить обе ступени по одному меню: кого греем первым и кого включит Enter.

    Ступень взятия вызывается настоящая. Подделан ровно пульт: терминал есть, ответа
    номером человек не даёт - это и есть Enter. Вопрос без дефолта подделка отличает от
    ответа сама (:meth:`Outside.ask`), и он тут законный исход, а не сбой щупа.
    """
    item = Seam(query=query, plans=len(plans))
    if not plans:
        return item
    args = Args(query=query.split())
    # Цель прогрева спрашивается ровно так, как её спрашивает боевой путь
    # (:func:`~torrcast.usecases.cast_command._choose._choose`), а ступень взятия ниже -
    # отдельно и сама: приговор ей НЕ подсовывается, иначе щуп сравнивал бы число с
    # самим собой и молчал бы о любом расхождении.
    order = warm_order(plans, enter_take(plans, args.title_query, None, False))
    item.warmed = named(order[0])
    head = {plan.picture.key for plan in order[:PREWARM]}
    world = Outside(tty=True)
    try:
        with outside(world):
            taken = _pick_plan(plans, None, pick=None, asked=args.title_query, menu=False)
            item.taken = named(taken)
            item.warm_head = taken.picture.key in head
            item.alive = liveliness(taken)
    except AssertionError:
        item.refused = "вопрос без дефолта: Enter не берёт ничего"
    except Exception as exc:
        item.refused = f"отказ: {exc}"
    return item


def report(items: list[Seam]) -> list[str]:
    """Числа замера: расхождений столько-то, цена в секундах такая-то."""
    menus = [item for item in items if item.plans > 1]
    diverged = [item for item in menus if item.diverged]
    cold = [item for item in diverged if not item.warm_head]
    warm = [item for item in diverged if item.warm_head]
    dead = [item for item in cold if item.alive < ALIVE_SEEDERS]
    costs = [item.cost for item in cold]
    out = [
        f"запросов в корпусе: {len(items)}, из них меню с выбором (картин > 1): {len(menus)}",
        f"🔴 цель прогрева разошлась со ступенью взятия: {len(diverged)} из {len(menus)}"
        f" (оценка снизу: офлайн ходит только первый круг)",
        f"    взятая картина вне прогретой головы (подъём с нуля): {len(cold)}",
        f"    взятая в голове, но без запасного релиза: {len(warm)}",
        f"    из холодных с молчащим роем (сидов < {ALIVE_SEEDERS}): {len(dead)}",
        f"цена зрителю: {sum(costs):.1f} с всего"
        + (f", медиана {statistics.median(costs):.1f} с на расхождение" if costs else ""),
    ]
    if cold:
        out.append("")
        out.append(f"{'запрос':<24}{'греем':<30}{'включит Enter':<30}{'сиды':>5}{'цена, с':>9}")
        for item in sorted(cold, key=lambda seam: -seam.cost):
            out.append(
                f"{item.query[:23]:<24}{item.warmed[:29]:<30}{item.taken[:29]:<30}"
                f"{item.alive:>5}{item.cost:>9.1f}"
            )
    if warm:
        out.append("")
        out.append("в прогретой голове, потерян только запасной релиз (цена лишь на браке верха):")
        for item in warm:
            out.append(f"  {item.query}: греем «{item.warmed}», включит Enter «{item.taken}»")
    return out


def main(argv: list[str] | None = None) -> int:
    # Тракт отбора сценарию раздаёт композиционный корень: без него первый же вопрос
    # сценария внешнему миру падает на несобранной среде.
    wire()
    ap = argparse.ArgumentParser(description="цель прогрева против ступени взятия (TC-829)")
    ap.add_argument("pools", type=Path, help="pools.jsonl со снятыми выдачами индексеров")
    ap.add_argument("--jsonl", type=Path, help="куда положить разбор построчно")
    add_profile_argument(ap)
    args = ap.parse_args(argv)

    config, choice = choose_profile(load_config(), args.profile)
    items: list[Seam] = []
    for line in args.pools.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record: dict[str, Any] = json.loads(line)
        query = str(record.get("query", ""))
        item = replay(query, batches_of(record), config, choice.profile, capped_of(record), query)
        items.append(seam_of(query, item.plans))

    print("\n".join(report(items)))
    if args.jsonl is not None:
        args.jsonl.write_text(
            "".join(
                json.dumps(
                    {
                        "query": item.query,
                        "plans": item.plans,
                        "warmed": item.warmed,
                        "taken": item.taken,
                        "refused": item.refused,
                        "warm_head": item.warm_head,
                        "alive": item.alive,
                        "diverged": item.diverged,
                        "cost": item.cost,
                    },
                    ensure_ascii=False,
                )
                + "\n"
                for item in items
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
