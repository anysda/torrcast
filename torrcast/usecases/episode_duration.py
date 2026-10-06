"""Длительность и паспорт следующей серии: своей она не знает, читаем из потока.
Зовёт цикл юнита показа перед каждой серией.
"""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.episode_passport import episode_passport
from torrcast.domain.worker_settings import WORKER_DUR
from torrcast.ports.prober import Prober
from torrcast.ports.state_store.slot import store
from torrcast.usecases.rank.reselect_voice import reselect_voice

#: Чем читается паспорт потока. Кладёт сюда композиционный корень
#: (:mod:`torrcast.runtime.wire`): без него следующая серия не узнала бы своей длительности.
_episode_prober: Prober


def _configure_episode_duration(prober: Prober) -> None:
    """Назначить, чем сценарий читает паспорт следующей серии."""
    global _episode_prober
    _episode_prober = prober


def _duration(key: str, entry: Entry, source: str, audio_source: str = "") -> Entry:
    """Длительность серии для порога перехода: следующая серия своей ещё не знает —
    её длительность лежит в её же файле, и читается она из потока, как дорожки.

    Тем же ffprobe берётся и вес видеодорожки (:attr:`Entry.vbps`): у следующей серии
    он свой, а профиль тяжести показа считается по нему.

    ⚠️ Ради одного только веса дорожки ffprobe тут не зовётся. Записи прежних версий его
    не несут, и спрашивать за них при каждом запуске значило бы платить секундами старта
    (у «Моаны 2» ffprobe стоит до 17 с) за то, что показ и так доберёт по факту
    (:meth:`torrcast.adapters.recode.weights.Weights.calibrate`). Своё число такая запись получит на
    первом же обычном запуске через выбор релиза.

    🔴 Ради глубины цвета (:attr:`Entry.depth`) ffprobe зовётся и у записи с известной
    длительностью - ровно один раз на запись. Записи прежних версий её не несут вовсе, а
    молчание тут читается как «восемь бит», то есть как «уезжай копией»: на десятибитном
    H.264 это вечная петля на экране (:func:`torrcast.domain.recodes_whole.recodes_whole`). Один
    ffprobe против неиграющего показа - цена, которую платить стоит, и платится она однажды.

    🔴 TC-251. Тем же одним ffprobe добирается и кадр (:attr:`Entry.frame`) - ровно по
    той же причине. Запись прежней версии его не несёт, а без кадра перекод не знает,
    надо ли ужимать картинку под потолок приёмника
    (:attr:`torrcast.adapters.recode.encode.Encode.ceiling`): 4К уезжало бы во весь свой
    кадр, и окно у этого ровно одно - первое продолжение старой записи. Лишнего запроса
    это не стоит: паспорт и так читается один раз на запись ради глубины, кадр лежит в нём же.
    """
    if entry.dur > 0 and entry.depth > 0 and entry.frame > 0:
        return entry
    # Паспорт в запись - тем же правилом, каким его видит прогрев следующей серии
    # (:func:`torrcast.domain.episode_passport.episode_passport`): вес видео, кодек, глубина,
    # кадр и HDR у этой серии свои, а разойдись они с прогревом - прогретое не найдётся.
    passport = _episode_prober(source, timeout=WORKER_DUR)
    sound = _episode_prober(audio_source, timeout=WORKER_DUR) if audio_source else passport
    measured = reselect_voice(episode_passport(entry, passport), sound)
    # Правка на месте, как и прежде: запись держит не только этот вызов.
    for name in ("audio", "dur", "vbps", "vbps_estimated", "codec", "depth", "frame", "hdr"):
        setattr(entry, name, getattr(measured, name))
    state = store().load()
    state.put(key, entry)
    store().save(state)
    return entry
