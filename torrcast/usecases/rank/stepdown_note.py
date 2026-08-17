"""Строка о том, что показ едет ступенью ниже доступной; зовёт строка запуска."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, TypeAlias

from torrcast.domain.media import Media
from torrcast.usecases.rank.drop_reason import drop_reason
from torrcast.usecases.rank.is_disc import is_disc
from torrcast.usecases.rank.misses_episode import misses_episode

if TYPE_CHECKING:
    _Plan: TypeAlias = Any


#: Насколько чужое обещание должно превышать наш кадр, чтобы считаться ступенью выше.
#: 1080 против 1078 — не ступень, а округление разных рипов одного и того же мастера.
STEP_RATIO: Final = 0.95


def stepdown_note(
    plan: _Plan,
    number: int,
    media: Media | None,
    queue: list[int],
    judged: dict[int, str] | None = None,
    reached: int = 0,
) -> str:
    """Одна строка о том, что показ едет ступенью НИЖЕ, чем в выдаче было доступно.

    🔴 TC-187. «Интерстеллар», «Форрест Гамп», «Зелёная миля», «Нелюбовь» доезжали в
    720p и SD при живых 1080p в той же выдаче — и ни одна строка об этом не говорила.
    Молчаливых подмен нет: снижение ступени — такое же авто-решение, как выбор релиза,
    и человек обязан услышать не только «что взяли», но и «почему не лучшее».

    Взятое меряется ПАСПОРТОМ, а не именем: ffprobe уже прочитан, и «названный 1080p, а
    внутри 574p» обязан считаться SD, иначе строка молчала бы ровно там, где подмена и
    случилась. Соседей мерить нечем, кроме имени, — их паспорта нет и не будет, пока их
    не подняли; поэтому у них берётся заявка, а порог :data:`STEP_RATIO` не даёт считать
    ступенью разницу в округлении.

    Причина — из того, чем кончилась их очередь:

    - ``отбраковали`` — раздачу трогали, и ffprobe (или рой) её осудил; приговор в строке;
    - ``не дошли`` — стояла в очереди, но до неё не добрались: годный нашёлся раньше;
    - ``в очередь не попал`` — выкинули воротами ещё до каста (:func:`drop_reason`);
    - ``рой мёртв`` — лучшее в выдаче есть, а сидов у него ноль: это не показ.

    Лучшего не было — строки нет вовсе: сообщать нечего, а лишняя строка на каждом
    показе обесценивает все остальные.
    """
    judged = judged or {}
    taken = plan.ranked[number - 1]
    frame = media.frame if media is not None and media.height else taken.height
    better = [
        (n, r)
        for n, r in enumerate(plan.ranked, start=1)
        if n != number
        and r.height * STEP_RATIO > frame
        and not misses_episode(r, plan.want)
        and not is_disc(r)
    ]
    if not better:
        return ""
    alive = [(n, r) for n, r in better if r.seeders > 0]
    best = max(alive or better, key=lambda pair: (pair[1].height, pair[1].seeders))
    at, rival = best
    if not alive:
        why = "рой мёртв"
    elif at in judged:
        why = f"отбраковали ({judged[at]})"
    elif at in queue:
        why = "не дошли" if queue.index(at) >= reached else "не ответил"
    else:
        why = f"в очередь не попал: {drop_reason(rival, plan)}"
    took = media.quality if media is not None and media.height else (taken.quality or "?")
    return f"взял {took}, рядом был {rival.quality} (релиз {at}, сидов {rival.seeders}) - {why}"
