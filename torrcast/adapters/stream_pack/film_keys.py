"""Снимает карту опорных кадров файла или берёт её с полки; спрашивают показ и прогрев."""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

from torrcast.adapters.frames.keyframes import keyframes
from torrcast.adapters.stream_pack._keys_shelf import _keys_cache
from torrcast.adapters.stream_pack.read_keys import read_keys
from torrcast.adapters.stream_probe import _trim
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.frames.keymap import KeyMap, video_track
from torrcast.domain.hls_wait import KEYS_WAIT
from torrcast.domain.warm_open import KEYS_KEPT, KEYS_LOCK
from torrcast.ports.journal import journal


def _fetching(lock: Path, ttl: float = KEYS_LOCK) -> bool:
    """Карту прямо сейчас снимает кто-то другой (прогрев под меню — соседний процесс).

    ``ttl`` - сколько замок считается живым. Числом, а не именем модуля: срок жизни
    замка тут - предмет измерения, и стенду он нужен в доли секунды, а не в минуту.
    """
    with contextlib.suppress(OSError):
        return time.time() - lock.stat().st_mtime < ttl
    return False


def _keys_draft(cache: Path) -> Path:
    """Черновик кэша карты - свой у каждого писателя.

    Замок на карту берётся не всегда (протух, каталог только для чтения), а на одно имя
    два писателя пишут вперемешку - и ``replace`` выложил бы наружу склейку двух половин.
    """
    return cache.with_suffix(f".{os.getpid()}-{threading.get_ident()}.tmp")


def _hold_keys_lock(lock: Path, done: threading.Event, ttl: float = KEYS_LOCK) -> None:
    """Держать замок карты живым, пока его хозяин работает: трогать mtime до ``done``."""
    while not done.wait(ttl / 3):
        with contextlib.suppress(OSError):
            lock.touch()


def film_keys(
    source_url: str,
    *,
    keys_of: Callable[[str], KeyMap] = keyframes,
    lock_ttl: float = KEYS_LOCK,
    wait: float = KEYS_WAIT,
) -> FilmKeys:
    """Карта опорных кадров видео: из кэша или из индекса контейнера.

    Индекс снимает :mod:`torrcast.adapters.frames.keyframes`.

    Если карту уже снимает прогрев (:func:`warm_file`), ждём его, а не читаем индекс
    файла вторым потоком: рой от этого быстрее не станет, а старт показа удвоится.

    ``keys_of`` - чем снимать индекс, ``lock_ttl`` и ``wait`` - сколько живёт замок и
    сколько ждать соседа. Все три названы параметром, а не именем внутри модуля: снятие
    индекса стоит Range-запросов в рой, а боевые сроки тут - минута и десятки секунд, и
    стенд обязан уметь назвать своё, не заглядывая модулю под крышку.
    """
    cache = _keys_cache(source_url)
    if (ready := read_keys(cache)) is not None:
        journal().mark("карта: из кэша")
        return ready
    lock = cache.with_suffix(".lock")
    deadline = time.monotonic() + wait
    waited = time.monotonic()
    while _fetching(lock, lock_ttl) and time.monotonic() < deadline:
        time.sleep(0.2)
        if (ready := read_keys(cache)) is not None:
            journal().mark("карта: дождались прогрева", ждали=round(time.monotonic() - waited, 2))
            return ready
    with contextlib.suppress(OSError):
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.touch()
    journal().mark("карта: чтение")
    # Замок живёт по mtime (:func:`_fetching`), поэтому его надо освежать, пока держим:
    # чтение хвоста у холодного роя стоит 2-6 с, но разбор карты добавляет к ним секунды,
    # и на длинном фильме замок протух бы прямо под работающим читателем - а сосед,
    # увидевший протухший замок, полез бы читать тот же хвост вторым потоком.
    holding = threading.Event()
    keeper = threading.Thread(target=_hold_keys_lock, args=(lock, holding, lock_ttl), daemon=True)
    keeper.start()
    # ⚠️ Замок снимается не после чтения, а после **записи кэша**: между ними лежит разбор
    # карты, и сосед, отпущенный раньше времени, кэша ещё не увидит и полезет читать хвост
    # сам. Ровно так холодный старт платил разбор дважды (замер: CLI и юнит
    # разбирали одну и ту же карту параллельно).
    try:
        found = keys_of(source_url)
        journal().mark("карта: снята", кадров=len(found.points), байт=found.taken)
        # ⚠️ Дорожку видео выбираем ОДИН раз. Пока этот вызов стоял внутри списка, он
        # считался на каждую точку Cues, а сам он линейный по всем точкам - то есть карта
        # разбиралась квадратично. Цена замерена: «Моана 2», 7274
        # точки - 18.5 с чистого процессора после того, как рой всё отдал. Ровно это и
        # принимали за «первое чтение хвоста у холодного роя»: рой отдаёт
        # Cues за 2-6 с, остальное было наше.
        track = video_track(found.points)
        video = [p for p in found.points if p.track == track]
        ready = FilmKeys(
            found.duration, [p.at for p in video], [p.offset for p in video], found.kind
        )
        with contextlib.suppress(OSError):
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = _keys_draft(cache)
            body = {
                "duration": ready.duration,
                "keys": ready.at,
                "bytes": ready.offset,
                "kind": ready.kind,
            }
            try:
                tmp.write_text(json.dumps(body), "utf-8")
                tmp.replace(cache)
            finally:  # своё имя не должно превратиться в свой же мусор на полке
                tmp.unlink(missing_ok=True)
        # Подрезка идёт после записи, а не до: только что снятая карта - самая свежая на
        # полке, и подрезать раньше значило бы мерить полку без неё.
        _trim(cache.parent, KEYS_KEPT)
    finally:
        holding.set()
        with contextlib.suppress(OSError):
            lock.unlink(missing_ok=True)
    return ready
