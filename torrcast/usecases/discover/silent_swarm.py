"""Отказ, когда ни одна тронутая раздача не отозвалась ни метаданными, ни потоком."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.rank.misses_episode import misses_episode
from torrcast.usecases.rank.over_ceiling import over_ceiling

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def silent_swarm(
    plan: Plan, queue: list[int], touched: int, shown: str, *, picked: int | None = None
) -> str:
    """Отказ, когда ни одна тронутая раздача не отозвалась ни метаданными, ни потоком.

    Прежде это была одна строка на все случаи - «рой у них мёртв, пиров нет». С виду
    честная, она врала чаще прежней: в замере каталога такой вердикт получили 18
    запросов из 225, и у девяти из них рой был ЖИВОЙ - просто очередь отбора кончилась
    на трёх раздачах из пятнадцати, а «пиров нет» было сказано про всю выдачу.

    Очередь отбора (:meth:`Plan.candidates`) - это не вся выдача: мимо неё проходят
    раздачи с чужой серией, образы дисков, слишком тяжёлые. Молчание тех, кого
    потрогали, не говорит ни слова о тех, кого не трогали. Поэтому строк пять, и
    различает их не догадка, а счётчики:

    * сидов не числится ни у одной раздачи картины - пиров правда нет, и сказать так
      можно честно;
    * обход не дошёл до конца очереди: его остановил потолок фазы
      (:data:`PICK_BUDGET`), и сколько именно раздач осталось неспрошенными, строка
      называет числом (TC-435);
    * потрогали всю выдачу до последней - молчат все, кого вообще можно было спросить,
      но сиды у них числились: это молчание роя, а не пустой каталог;
    * нетронутое осталось, но всё оно непригодно по уже ИЗВЕСТНЫМ признакам - нужной
      серии нет по имени раздачи или она тяжелее потолка (TC-375): играть в нём
      нечего, и строка говорит об этом прямо, ручного выбора не предлагая. Замер по
      сохранённым прогонам: у таких отказов 132 нетронутые раздачи из 195 не
      содержали запрошенной серии вовсе;
    * нетронутое осталось, и пригодное в нём есть - про него мы не знаем ничего, и
      врать за него нельзя. Человеку остаётся ручной выбор, и строка говорит, чем
      именно он располагает.

    Числа в строке - всегда два: сколько раздач было в выдаче и сколько потрогали.
    Сиды называются как обещание индексера («числится»), а не как факт: раздача,
    которая молчит поток, показывает в выдаче сотню сидов ровно так же бодро. И
    числится максимум по ОЧЕРЕДИ, а не по всей выдаче (TC-376): иначе число ложилось
    на раздачу, которую ворота в очередь не пустили вовсе, и выглядело уликой против
    роя («числится 25, а молчат»), уликой не будучи. Исключение - первая строка: её
    «пиров нет ни у одной» сказано про всю выдачу и считается по всей выдаче.

    🔴 Ход человеку предлагает КАЖДАЯ из строк, и ходы эти разные, потому что разное
    осталось непроверенным. Там, где отбор до пригодной части выдачи не дошёл, ход -
    ручной выбор: непроверенные раздачи есть, и они рядом. Там, где потрогали всё или
    где нетронутое заведомо непригодно, ручной выбор врал бы надеждой - выбирать не
    из чего, и честный ход другой: назвать картину иначе (другой запрос собирает
    другую выдачу) или вернуться позже, когда рой проснётся. Отказ без хода - это
    тупик, в котором человек остаётся один; раньше таким был отказ по
    :data:`PEER_GRACE`, а он теперь и самый частый.

    Обход, срезанный часами, ход получает тот же - «иначе или позже», а не ручной
    выбор. Про неспрошенный хвост очереди неизвестно ничего, кроме одного: весь бюджет
    фазы ушёл на раздачи, которые стояли ВЫШЕ него и не отозвались ни одна. Указать на
    хвост номером значило бы выдать за подсказку то, чего мы не проверяли; сказать, что
    рой молчит и сколько раздач он молчит, - это факт.
    """
    total = len(plan.ranked)
    peers = max((plan.ranked[n - 1].seeders for n in queue), default=0)
    all_peers = max((release.seeders for release in plan.ranked), default=0)
    counts = phrase("discover.swarm_counts", total=total, touched=touched)
    later = phrase("discover.swarm_later")
    if all_peers <= 0:
        return phrase("discover.swarm_no_peers", counts=counts, later=later, shown=shown)
    if touched < len(queue):
        # 🔴 TC-435. Обход кончился не очередью, а часами (:data:`PICK_BUDGET`): дальше
        # головы дело не дошло, и приписывать молчание хвосту нельзя - его не спрашивали.
        # Числа тут два, и оба свои: сколько раздач отбор взял и сколько успел потрогать.
        return phrase(
            "discover.swarm_out_of_time",
            counts=counts,
            queue_len=len(queue),
            peers=peers,
            later=later,
            shown=shown,
        )
    queued = set(queue)
    untouched = [r for n, r in enumerate(plan.ranked, start=1) if n not in queued]
    # Причины - в порядке суда отбора (:func:`drop_reason`): у выкинутой их бывает
    # несколько сразу, а называется та, на которой её и выкинули.
    no_episode = [r for r in untouched if misses_episode(r, plan.want)]
    heavy = [
        r
        for r in untouched
        if not misses_episode(r, plan.want)
        and over_ceiling(r, plan.runtime, plan.warn_mbit, plan.hard_mbit)
    ]
    if len(untouched) > len(no_episode) + len(heavy):
        seed = (
            phrase("discover.swarm_seed_some", peers=peers)
            if peers
            else phrase("discover.swarm_seed_none")
        )
        move = (
            phrase("discover.swarm_pick_other")
            if picked is not None
            else phrase("discover.swarm_pick_manual")
        )
        return phrase(
            "discover.swarm_untouched_some", counts=counts, seed=seed, move=move, shown=shown
        )
    if not untouched:
        return phrase(
            "discover.swarm_all_silent", counts=counts, peers=peers, later=later, shown=shown
        )
    why = [phrase("discover.swarm_reason_no_episode", count=len(no_episode))] if no_episode else []
    why += [phrase("discover.swarm_reason_heavy", count=len(heavy))] if heavy else []
    return phrase(
        "discover.swarm_untouched_unfit",
        counts=counts,
        reasons=", ".join(why),
        later=later,
        shown=shown,
    )
