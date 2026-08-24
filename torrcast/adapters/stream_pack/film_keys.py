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
from torrcast.adapters.stream_pack.refused_keys import refused_keys
from torrcast.adapters.stream_probe.shelf import _trim
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.frames.keymap.key_map import KeyMap
from torrcast.domain.frames.keymap.video_track import video_track
from torrcast.domain.hls_wait import KEYS_WAIT
from torrcast.domain.infra_error import InfraError
from torrcast.domain.swarm_silent_error import SwarmSilentError
from torrcast.domain.warm_open import KEYS_KEPT, KEYS_LOCK, KEYS_REFUSED
from torrcast.ports.journal.slot import journal


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


def _mark_refusal(cache: Path, refused: str) -> None:
    """Положить на полку вердикт «карты с этого файла не будет» - на место самой карты.

    Пишется через тот же черновик, что и карта (:func:`_keys_draft`): имя на полке одно, и
    два писателя на одно имя пишут вперемешку.
    """
    with contextlib.suppress(OSError):
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = _keys_draft(cache)
        try:
            tmp.write_text(json.dumps({"refused": refused, "when": time.time()}), "utf-8")
            tmp.replace(cache)
        finally:
            tmp.unlink(missing_ok=True)


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
    kept: int = KEYS_KEPT,
    refused_ttl: float = KEYS_REFUSED,
) -> FilmKeys:
    """Карта опорных кадров видео: из кэша или из индекса контейнера.

    Индекс снимает :mod:`torrcast.adapters.frames.keyframes`.

    Если карту уже снимает прогрев (:func:`warm_file`), ждём его, а не читаем индекс
    файла вторым потоком: рой от этого быстрее не станет, а старт показа удвоится.

    Отказ кладётся на полку рядом с картами и на то же имя: «индекс врёт», «индекса нет»,
    «контейнер незнакомый» - это ответы про сам файл, и до следующего старта они не
    меняются. Без этого каждый старт такого фильма платил заново - голову, весь индекс и
    пробы честности, - а сессия с прогревом и показом платила дважды. Молчание роя
    (:class:`~torrcast.domain.swarm_silent_error.SwarmSilentError`) не запоминается: оно не про
    файл.

    ``keys_of`` - чем снимать индекс, ``lock_ttl`` и ``wait`` - сколько живёт замок и
    сколько ждать соседа, ``kept`` - сколько карт остаётся на полке, ``refused_ttl`` -
    сколько помнится отказ. Все пять названы параметром, а не именем внутри модуля:
    снятие индекса стоит Range-запросов в рой, боевые сроки тут - минута, десятки секунд
    и сутки, а боевой потолок полки - 256 карт, и стенд обязан уметь назвать своё, не
    заглядывая модулю под крышку.
    """
    cache = _keys_cache(source_url)
    if (ready := read_keys(cache)) is not None:
        journal().mark("карта: из кэша")
        return ready
    if (refused := refused_keys(cache, refused_ttl)) is not None:
        journal().mark("карта: отказ с полки")
        raise InfraError(refused)
    lock = cache.with_suffix(".lock")
    deadline = time.monotonic() + wait
    waited = time.monotonic()
    while _fetching(lock, lock_ttl) and time.monotonic() < deadline:
        time.sleep(0.2)
        if (ready := read_keys(cache)) is not None:
            journal().mark("карта: дождались прогрева", ждали=round(time.monotonic() - waited, 2))
            return ready
        # Сосед может кончить и отказом - тогда ждать больше нечего, и читать хвост
        # самому тем более незачем: ответ про файл у нас уже есть.
        if (refused := refused_keys(cache, refused_ttl)) is not None:
            journal().mark("карта: сосед отказал", ждали=round(time.monotonic() - waited, 2))
            raise InfraError(refused)
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
        # Дорожку называет сам файл (элемент Tracks у mkv); эвристика - запасной путь
        # на случай головы без Tracks.
        track = found.video if found.video is not None else video_track(found.points)
        video = [p for p in found.points if p.track == track]
        # Исковое время лежит в том же порядке, что точки, и фильтруется вместе с ними;
        # пустое - равно меткам показа (mkv, mp4 со списком правок).
        via = (
            tuple(v for p, v in zip(found.points, found.via, strict=True) if p.track == track)
            if found.via
            else ()
        )
        ready = FilmKeys(
            found.duration,
            [p.at for p in video],
            [p.offset for p in video],
            found.kind,
            via,
        )
        with contextlib.suppress(OSError):
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = _keys_draft(cache)
            body = {
                "duration": ready.duration,
                "keys": ready.at,
                "bytes": ready.offset,
                "kind": ready.kind,
                "via": list(ready.via),
            }
            try:
                tmp.write_text(json.dumps(body), "utf-8")
                tmp.replace(cache)
            finally:  # своё имя не должно превратиться в свой же мусор на полке
                tmp.unlink(missing_ok=True)
        # Подрезка идёт после записи, а не до: только что снятая карта - самая свежая на
        # полке, и подрезать раньше значило бы мерить полку без неё.
        _trim(cache.parent, kept)
    except SwarmSilentError:
        raise  # рой молчит: про файл это не говорит ничего, помнить нечего
    except InfraError as no:
        # Приговор самому файлу. Он лежит на месте карты, поэтому полку подрезаем и тут:
        # иначе фильмы, которым карты не будет, растили бы её мимо потолка.
        journal().mark("карта: отказ", почему=str(no))
        _mark_refusal(cache, str(no))
        _trim(cache.parent, kept)
        raise
    finally:
        holding.set()
        with contextlib.suppress(OSError):
            lock.unlink(missing_ok=True)
    return ready
