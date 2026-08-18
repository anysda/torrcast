"""Сиды лучшей раздачи, которой картину и правда стоит смотреть."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice.configure import _environment_port

if TYPE_CHECKING:
    from torrcast.usecases.select._plan import _Plan


def fitness(plan: _Plan, dubbed: bool = False) -> int:
    """Сиды лучшей раздачи, которой картину и правда стоит смотреть; 0 - такой нет.

    От :func:`liveliness` отличается двумя условиями, и оба взяты у самого отбора, а не
    придуманы заново:

    * раздача ЖИВА - сидов не меньше :data:`ALIVE_SEEDERS`. Живость картины считается
      этим же порогом (:func:`alive_numbers`), и второго значения у слова тут нет;
    * раздача НЕ СТАРЬЁ - :func:`is_dated`. Это тот самый приговор, который отбор выносит
      каждой строке: XviD и DVDRip, названная ступень ниже :data:`HD_HEIGHT`, молчаливое
      имя при SD-битрейте.

    Нужна она там, где вопрос не «кто живее», а «состоится ли вечер вообще»: пул, в
    котором ни одной такой раздачи нет, годным не бывает (:func:`unfit_pool`), а картина
    без единой такой раздачи - тупик, и дефолт меню на неё не садится, когда рядом стоит
    живая тёзка (:func:`playable`).

    ⚠️ Порядок отбора это НЕ смягчает и не ужесточает: годность релиза по-прежнему решает
    :func:`is_candidate`, а старьё по-прежнему играется, когда другого нет вовсе. Здесь
    считается только вес картины в двух вопросах выше.

    ``dubbed`` - считать только раздачи, чьё ИМЯ обещает русскую дорожку
    (:attr:`~torrcast.domain.release.Release.dubbed`). Тем же словом «стоит смотреть» отвечают на
    третий вопрос - «состоится ли вечер ПО-РУССКИ» (:func:`voiceless_pool`): русская дорожка
    входит в «включилось» (TC-178), и пул без единой играбельной раздачи с нею - такой же
    тупик, как пул без единой играбельной вовсе.
    """
    return max(
        (
            release.seeders
            for release in plan.ranked
            if release.seeders >= _environment_port().alive_seeders
            and (release.dubbed or not dubbed)
            and _environment_port().is_candidate(
                release,
                plan.runtime,
                plan.warn_mbit,
                plan.loose,
                plan.hard_mbit,
                copy_hevc=plan.copy_hevc,
            )
            and not _environment_port().is_dated(release, plan.runtime)
        ),
        default=0,
    )
