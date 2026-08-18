"""Отказ отбора: чем он кончился и какой у человека ход. Молчаливого отказа не бывает."""

from __future__ import annotations

from typing import NoReturn

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.pick_settings import MAX_TRIES
from torrcast.usecases.discover.kin_line import kin_line
from torrcast.usecases.discover.silent_swarm import silent_swarm
from torrcast.usecases.select.plan import Plan


def _bench_refusal(
    plan: Plan,
    queue: list[int],
    tried: list[str],
    silents: int,
    exhausted: bool,
    picked: int | None,
) -> NoReturn:
    """Отказ обхода очереди: молчание роя и «годного нет» - это разные отказы.

    Ни один тронутый релиз не дошёл до приговора - ffprobe не прочитал ни одного, потому
    что не приехали ни метаданные по DHT, ни поток. Раздачи есть и по именам годны -
    молчит рой, а не выбор, и врать «годного релиза нет» тут нельзя. Но и «рой мёртв» на
    всю выдачу - враньё ровно так же: очередь отбора это НЕ вся выдача, и сколько из неё
    потрогали, знают только счётчики - их и печатает :func:`silent_swarm`.

    🔴 TC-435. Исчерпания очереди ветка не ждёт. Обход 60 молчащих роёв «Дюны», вставший
    по часам (:data:`PICK_BUDGET`), кончался словами «годного релиза нет» - а негодных не
    нашли ни одного: их не прочитали. Молчание роя названо молчанием роя независимо от
    того, кончилась очередь или кончилось время.

    🔴 TC-399. Ветка - только когда промолчали ВСЕ тронутые. Приговор осмотра
    («отдельного видеофайла нет», «нужной серии нет») молчанием роя не является: про
    такую раздачу известно всё, и «зайди позже - рой оживёт» было бы ложью.
    """
    shown = "; ".join(tried[:MAX_TRIES])
    more = f" и ещё {len(tried) - MAX_TRIES}" if len(tried) > MAX_TRIES else ""
    offer = kin_line(plan.kin)
    tail = f"\n{offer}" if offer else ""
    if silents == len(tried) and tried:
        raise NotFoundError(
            silent_swarm(plan, queue, len(tried), f"{shown}{more}", picked=picked) + tail
        )
    refused = f"годного релиза нет ({shown}{more})"
    if exhausted and len(set(queue)) == len(plan.ranked):
        if offer:
            raise NotFoundError(refused + tail)
        raise NotFoundError(
            refused + ": назови картину иначе - другой запрос соберёт другую выдачу"
        )
    move = "выбери другой релиз" if picked is not None else "выбери руками"
    raise NotFoundError(
        f"{refused}: {move} - cast releases <запрос>, потом cast <запрос> --release N" + tail
    )
