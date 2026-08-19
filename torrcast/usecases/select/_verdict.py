"""Приговоры отбора и осечки роя: что попадает в след и как зовётся человеку."""

from __future__ import annotations

import re

from torrcast.domain.swarm_error import SwarmError
from torrcast.ports.journal.slot import journal
from torrcast.usecases.select._prep import _Prep


def _turned_down(judged: dict[int, str], number: int, why: str) -> None:
    """Релиз отвергнут: приговор запомнить и положить в след - ровно один раз на решение.

    🔴 TC-194. Единственное место, где рождается запись ``select/drop``, и заведено оно
    затем, чтобы отказ не мог напечататься мимо следа. Так и было: очередь отбора
    (:meth:`Bench.resolve`) писала запись, а проверка честности (:meth:`Bench._honest`)
    печатала свои отказы молча - «Наруто» кончился одной строкой на экране и нулём
    событий в недельной ленте, то есть след говорил, что отбор прошёл без единой осечки.

    ``judged`` - те же приговоры по номерам, которыми потом объясняется снижение ступени
    (:func:`stepdown_note`): релиз, которого мы коснулись, обязан числиться отбракованным,
    а не «не дошли».
    """
    judged[number] = why
    journal().emit("select", "drop", release=number, why=why)


def _did_not_answer(number: int, why: str) -> None:
    """Записать осечку роя, не превращая наше ожидание в приговор раздаче."""
    journal().emit("select", "drop", release=number, why=why)


def _waiting_note(prep: _Prep, why: str) -> str:
    """Назвать окончившееся терпение, а не объявлять неизвестный рой пустым."""
    if not _silenced(prep):
        return why
    matched = re.search(r"за (\d+) с", why)
    return f"не дождались за {matched.group(1)} с" if matched else "не дождались"


def _silenced(prep: _Prep | None) -> bool:
    """Осечка ли это РОЯ: про сам релиз мы так ничего и не узнали.

    Отличается тем же, чем отличаются две осечки отбора (:meth:`Bench.resolve`): ffprobe
    паспорт прочитал - про релиз известно всё, и второй раз спрашивать нечего; рой
    промолчал - неизвестно ничего, кроме того, что раздача не отозвалась. Опознаётся
    ТИПОМ отказа, а не текстом: текст пишется языком зрителя и правится (TC-281).

    «Нужной серии в раздаче нет» и «отдельного видеофайла нет» - это
    :class:`~torrcast.domain.not_found_error.NotFoundError`: про раздачу узнали всё, что хотели, и
    терпение ей ничего не добавит. Молчание роя приезжает
    :class:`~torrcast.domain.swarm_error.SwarmError`, а не уложившаяся в бюджет фаза - вовсе без
    отказа, одной строкой :attr:`_Prep.error`.
    """
    if prep is None or prep.media is not None:
        return False
    return prep.failure is None or isinstance(prep.failure, SwarmError)
