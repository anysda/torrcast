"""Играется ли записанная раздача вообще: порог между «медленно» и «мертво»."""

from __future__ import annotations

import time

import torrcast.usecases.select._pick_state as _pick_state
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.worker_settings import WORKER_META
from torrcast.ports.journal.slot import journal
from torrcast.ports.progress.slot import progress as progress_bar
from torrcast.usecases.select._voiced import _Voiced


def _dead_release(config: Config, entry: Entry, own: _Voiced) -> str:
    """Почему записанная раздача не сыграет; пусто - сыграет, продолжаем как продолжали.

    🔴 **Признаков ровно два, и оба однозначны.** Метаданные не приехали за
    :data:`~torrcast.domain.worker_settings.WORKER_META` - раздачи больше нет ни у кого;
    метаданные приехали, а файла с записанным номером
    (:attr:`torrcast.domain._playing._Playing.file_idx`) в них нет - в этой раздаче играть
    нечего. Второй стоит миллисекунды после первого, первый в худшем случае - минуту
    вместо шести (:data:`torrcast.usecases.start_budget.START_BUDGET`).

    **Почему порог именно WORKER_META, а не свой.** Это тот же последний рубеж, что стоит
    ВНУТРИ юнита показа: магнит юниту отдан, метаданные не приехали - показывать нечего.
    Значит ложного отказа относительно показа тут не бывает по построению: всё, что мы
    отвергаем здесь, юнит не сыграл бы и сам, только сказал бы об этом на пять минут позже
    и уже некому. Цена ошибки в другую сторону - минута ожидания на мёртвой записи -
    заплачена сознательно.

    **Что отвергнуто и почему.** Отсрочка «рой пуст»
    (:data:`torrcast.domain.pick_settings.SWARM_GRACE`) дала бы приговор за 12 с, но по
    замеру, записанному рядом с ней, ложных приговоров у неё 15 из 26: в отборе такая
    ошибка стоит места в очереди, а здесь - ухода с уже прогретого места на релиз,
    который надо греть с нуля. Ложный отказ хуже отказа вовсе, поэтому отсрочка не
    берётся. «Байты не текут» неоднозначен: скорость роя гуляет на порядок, и порога,
    отделяющего медленную живую раздачу от мёртвой, у него нет. «Показ не дал картинки за
    срок» - это и есть сегодняшняя беда, шесть минут черноты.

    🔴 **Приговор выносится по названному ТИПУ отказа** (:class:`SwarmError` - «раздача не
    отдала метаданные»), а любой другой отказ службы читается как «спросить не удалось» и
    записанному релизу не вменяется. Мёртвый TorrServer
    (:class:`torrcast.domain.server_down_error.ServerDownError`) относится ко всей очереди
    сразу, и перебирать через него релизы бессмысленно; такой запуск идёт ровно туда же,
    куда шёл до этой проверки, и о службе скажет сам. Обратное правило («не ответили -
    значит мертво») хоронило бы живую запись каждый раз, когда служба перезапускается.

    ⚠️ Живой записи проверка почти ничего не стоит: метаданные всё равно первым делом
    читает юнит, а после нашего ``add`` они у службы уже есть. Раздача при этом
    поднимается НАШИМ вызовом, поэтому хэш её сразу записывается хозяину (``own``): не
    сыграла - её уберёт он же (:meth:`_Voiced.drop`), сыграла - примет юнит.

    Каждый из трёх исходов отмечается в следе с временем и причиной: «жива» и «спросить
    не удалось» снаружи неотличимы (обе возвращают пусто), и без отметки цену проверки
    на счастливом пути - а она стоит на пути каждого зрителя - не назвать числом.
    """
    torrserver = _pick_state._select_engines(config.torrserver_url)
    started = time.monotonic()
    try:
        with progress_bar() as progress:
            progress.phase("раздача")
            own.torrent_hash = torrent_hash = torrserver.add(entry.magnet)
            files = torrserver.wait_files(torrent_hash, timeout=WORKER_META)
    except SwarmError as refused:
        verdict, how, why = str(refused), "похоронена", str(refused)
    except TorrcastError as failed:
        # спросить не удалось - это не ответ «мертво», и записанное играет как играло
        verdict, how, why = "", "не спрошена", str(failed)
    else:
        if any(found.index == entry.file_idx for found in files):
            verdict, how, why = "", "жива", ""
        else:
            verdict = f"файла №{entry.file_idx} в ней больше нет"
            how, why = "похоронена", verdict
    journal().mark(
        "записанная раздача",
        исход=how,
        причина=why,
        секунд=round(time.monotonic() - started, 1),
    )
    return verdict
