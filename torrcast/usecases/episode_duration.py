"""Длительность и паспорт следующей серии: своей она не знает, читаем из потока.
Зовёт цикл юнита показа перед каждой серией.
"""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.worker_settings import WORKER_DUR
from torrcast.ports.prober import Prober
from torrcast.ports.state_store import store

#: Чем читается паспорт потока. Кладёт сюда композиционный корень
#: (:mod:`torrcast.runtime.wire`): без него следующая серия не узнала бы своей длительности.
_episode_prober: Prober


def _configure_episode_duration(prober: Prober) -> None:
    """Назначить, чем сценарий читает паспорт следующей серии."""
    global _episode_prober
    _episode_prober = prober


def _duration(key: str, entry: Entry, source: str) -> Entry:
    """Длительность серии для порога перехода: следующая серия своей ещё не знает —
    её длительность лежит в её же файле, и читается она из потока, как дорожки.

    Тем же ffprobe берётся и вес видеодорожки (:attr:`Entry.vbps`): у следующей серии
    он свой, а профиль тяжести показа считается по нему.

    ⚠️ Ради одного только веса дорожки ffprobe тут не зовётся. Записи прежних версий его
    не несут, и спрашивать за них при каждом запуске значило бы платить секундами старта
    (у «Моаны 2» ffprobe стоит до 17 с) за то, что показ и так доберёт по факту
    (:meth:`torrcast.recode.Weights.calibrate`). Своё число такая запись получит на первом
    же обычном запуске через выбор релиза.

    🔴 Ради глубины цвета (:attr:`Entry.depth`) ffprobe зовётся и у записи с известной
    длительностью - ровно один раз на запись. Записи прежних версий её не несут вовсе, а
    молчание тут читается как «восемь бит», то есть как «уезжай копией»: на десятибитном
    H.264 это вечная петля на экране (:func:`torrcast.domain.recodes_whole.recodes_whole`). Один
    ffprobe против неиграющего показа - цена, которую платить стоит, и платится она однажды.

    🔴 TC-251. Тем же одним ffprobe добирается и кадр (:attr:`Entry.frame`) - ровно по
    той же причине. Запись прежней версии его не несёт, а молчание тут читается
    :func:`torrcast.recode.level_for` как «4.1»: на 4К это враньё в поток (у 2160p 32400
    макроблоков против потолка 8192), и окно у вранья ровно одно - первое продолжение
    старой записи. Лишнего запроса это не стоит: паспорт и так читается один раз на
    запись ради глубины, кадр лежит в нём же.
    """
    if entry.dur > 0 and entry.depth > 0 and entry.frame > 0:
        return entry
    media = _episode_prober(source, timeout=WORKER_DUR)
    entry.dur = media.duration or entry.dur
    # Ноль - «ещё не спрашивали», минус - «спросили, паспорт промолчал» (mp4 без тегов).
    entry.vbps = media.video_bps / 1e6 or -1.0
    # Кодек следующей серии тоже свой: в раздаче аниме нередко лежат и HEVC, и H.264,
    # а решение «перекодировать целиком» принимается по файлу, который играем сейчас.
    entry.codec = media.video or ""
    # Глубина цвета оттуда же и той же ценой: без неё Hi10P неотличим от обычного H.264.
    entry.depth = media.depth
    # И кадр тем же паспортом: без него 4К-запись прежней версии уезжала бы с уровнем
    # «4.1» в потоке - заведомым враньём (TC-251).
    entry.frame = media.frame
    state = store().load()
    state.put(key, entry)
    store().save(state)
    return entry
