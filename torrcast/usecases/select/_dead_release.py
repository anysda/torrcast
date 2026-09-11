"""Играется ли записанная раздача вообще: порог между «медленно» и «мертво»."""

from __future__ import annotations

import time
from contextlib import suppress
from typing import Any, cast

import torrcast.usecases.playback._show_state as _show_state
import torrcast.usecases.select._pick_state as _pick_state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.pick_settings import RECORDED_CONTACT
from torrcast.domain.swarm_alive import swarm_alive
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.clock import Clock
from torrcast.ports.journal.slot import journal
from torrcast.ports.progress.slot import progress as progress_bar
from torrcast.ports.torrent_engine import TorrentEngine
from torrcast.usecases.select._voiced import _Voiced

#: Шаг опроса роя, пока ждём первый контакт.
CONTACT_STEP = 0.5


def _dead_release(config: Config, entry: Entry, own: _Voiced, clock: Clock | None = None) -> str:
    """Почему записанная раздача не сыграет; пусто - сыграет, продолжаем как продолжали.

    🔴 **Признаков три, и все однозначны.** Метаданные не приехали за
    :data:`~torrcast.domain.pick_settings.RECORDED_CONTACT` - роя нет; метаданные есть, а
    файла с записанным номером (:attr:`torrcast.domain._playing._Playing.file_idx`) в них
    нет - играть нечего; файлы есть, но за тот же срок от ``add`` ни с одним пиром не
    поговорили (:func:`_heard`) - байта никто не отдаст. Третий признак нужен потому, что
    файлы служба знает и без роя: раздача легла в её базу при прошлом показе
    (``save_to_db``), и «метаданные приехали» у такой записи ничего не говорит о рое.

    **Почему срок RECORDED_CONTACT, а не последний рубеж юнита.** Раньше порогом стоял
    :data:`~torrcast.domain.worker_settings.WORKER_META` (60 с): ложного отказа относительно
    показа при нём не бывало по построению, но «Играть» на мёртвой записи стоил 85 с до
    кадра, а запись из базы службы проходила проверку мгновенно и шесть минут
    (:data:`torrcast.usecases.start_budget.START_BUDGET`) не давала ни кадра (TC-1203).
    Срок и цена ошибки замерены и записаны при самом числе; главное здесь - ошибка
    стоит не отказа: похороненная запись уступает поиску, а место переезжает на новый
    релиз (:func:`torrcast.usecases.cast_command._kept_dead._kept_dead`).

    **Что отвергнуто и почему.** Отсрочка «рой пуст»
    (:data:`torrcast.domain.pick_settings.SWARM_GRACE`, 12 с) даёт по замеру рядом с ней
    15 ложных приговоров из 26 - так часто уводить зрителя с его релиза нельзя. «Байты не
    текут» неоднозначен: скорость роя гуляет на порядок, и порога, отделяющего медленную
    живую раздачу от мёртвой, у него нет, - поэтому мерится состоявшийся контакт, а не
    скорость. «Показ не дал картинки за срок» - это и есть шесть минут черноты.

    🔴 **Приговор выносится по названному ТИПУ отказа** (:class:`SwarmError`), а любой
    другой отказ службы читается как «спросить не удалось» и записанному релизу не
    вменяется. Мёртвый TorrServer
    (:class:`torrcast.domain.server_down_error.ServerDownError`) относится ко всей очереди
    сразу, и перебирать через него релизы бессмысленно; такой запуск идёт ровно туда же,
    куда шёл до этой проверки, и о службе скажет сам. Обратное правило («не ответили -
    значит мертво») хоронило бы живую запись каждый раз, когда служба перезапускается.

    ⚠️ Раздача поднимается НАШИМ вызовом, поэтому хэш её сразу записывается хозяину
    (``own``): не сыграла - её уберёт он же (:meth:`_Voiced.drop`), сыграла - примет юнит.
    Живая запись платит за проверку только ожиданием первого контакта, который юниту
    всё равно нужен до первого байта.

    Каждый из трёх исходов отмечается в следе с временем и причиной: «жива» и «спросить
    не удалось» снаружи неотличимы (обе возвращают пусто), и без отметки цену проверки
    на счастливом пути - а она стоит на пути каждого зрителя - не назвать числом.
    ``clock`` - часы ожидания контакта; без него - часы, которые поставил корень.
    """
    torrserver = _pick_state._select_engines(config.torrserver_url)
    started = time.monotonic()
    try:
        with progress_bar() as progress:
            progress.phase(phrase("select.phase_release"))
            own.torrent_hash = torrent_hash = torrserver.add(entry.magnet)
            files = torrserver.wait_files(torrent_hash, timeout=RECORDED_CONTACT)
            kept = any(found.index == entry.file_idx for found in files)
            if kept:
                spent = time.monotonic() - started
                _heard(torrserver, torrent_hash, RECORDED_CONTACT - spent, clock)
    except SwarmError as refused:
        verdict, how, why = str(refused), "похоронена", str(refused)
    except TorrcastError as failed:
        # спросить не удалось - это не ответ «мертво», и записанное играет как играло
        verdict, how, why = "", "не спрошена", str(failed)
    else:
        if kept:
            verdict, how, why = "", "жива", ""
        else:
            verdict = phrase("select.file_gone", index=entry.file_idx)
            how, why = "похоронена", verdict
    journal().mark(
        "записанная раздача",
        исход=how,
        причина=why,
        секунд=round(time.monotonic() - started, 1),
    )
    return verdict


def _heard(
    torrserver: TorrentEngine, torrent_hash: str, budget: float, clock: Clock | None
) -> None:
    """Дождаться первого состоявшегося контакта роя; промолчал весь срок - :class:`SwarmError`.

    Спрашивается то же, что спрашивает отбор (:func:`swarm_alive`): «поговорили» - жива,
    «адреса есть, ни с кем не поговорили» весь срок - мертва. Служба, не сказавшая про рой
    ни слова, приговора не даёт, как не даёт его и отбору, а служба, которую спросить не
    удалось вовсе, отпускает сразу: это не ответ «мертво».
    """
    watch = clock
    began: float | None = None
    while True:
        asked, heard = _swarm_said(torrserver, torrent_hash)
        if not asked or heard:
            return
        watch = watch if watch is not None else _show_state.CLOCK
        began = watch.monotonic() if began is None else began
        left = began + budget - watch.monotonic()
        if left <= 0:
            break
        watch.sleep(min(CONTACT_STEP, left))
    if heard is False:
        raise SwarmError(
            phrase("torrserver.swarm_empty", seconds=f"{RECORDED_CONTACT:.0f}"),
            waited=RECORDED_CONTACT,
        )


def _swarm_said(torrserver: TorrentEngine, torrent_hash: str) -> tuple[bool, bool | None]:
    """Спросили ли службу о рое и что она сказала (:func:`swarm_alive`).

    Счётчиков роя в договоре службы нет: их знает только настоящий TorrServer, и
    спрашиваются они так же, как их спрашивает отбор, снимая предложение
    (:meth:`torrcast.usecases.select_bench._bench_work._BenchWork._sample_supply`).
    """
    with suppress(Exception):
        return True, swarm_alive(cast(Any, torrserver).status(torrent_hash))
    return False, None
