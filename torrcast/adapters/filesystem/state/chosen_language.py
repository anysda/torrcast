"""Свежий язык продукта из настройки, с безопасным английским умолчанием."""

from __future__ import annotations

import os
import threading
import time

from torrcast.adapters.filesystem.state.config_path import config_path
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.catalogs.tongue import EN
from torrcast.domain.torrcast_error import TorrcastError

#: Спрашивает ли ЭТОТ поток язык прямо сейчас. Флаг потоко-честный, потому что у
#: продукта есть щупы роя (:mod:`torrcast.usecases.select_bench._bench_work`): общий
#: на процесс флаг гасил бы язык соседу - пока один поток читает настройку, второй
#: получал бы английский на живой и вполне читаемой русской установке.
_asking = threading.local()
#: Последний прочитанный язык, отпечаток файла, из которого он прочитан, и когда
#: отпечаток сверяли в последний раз (часы :func:`time.monotonic`). Снимок неизменяемый
#: и меняется только целиком: читатель берёт его ОДИН раз и дальше смотрит в свою
#: копию. Проверка «запись есть» и чтение записи отдельными шагами роняли надпись
#: ``IndexError``-ом, когда бот писал язык (``cast --ru``) из соседнего потока.
_last: tuple[tuple[str, int, int, int], str, float] | None = None
#: Сколько раз снимок забывали записью настройки. Читатель запоминает прочитанное,
#: только если счёт не сдвинулся, пока он читал: начавший до записи иначе закрепил бы
#: старый язык на всё окно сверки. Сверка счёта и замена снимка идут одним шагом.
_epoch = 0
_swap = threading.Lock()
#: Сколько секунд язык верят без сверки с файлом. Надпись спрашивает язык на каждом
#: зове, и даже один ``stat`` на надпись копился на пути старта показа; чужой процесс
#: (``cast language``) меняет язык живого показа не позже этого окна.
_GLANCE = 1.0


def _forget_language() -> None:
    """Забыть прочитанный язык: запись настройки из этого же процесса видна сразу."""
    global _last, _epoch
    with _swap:
        _last = None
        _epoch += 1


def _keep(epoch: int, now: tuple[tuple[str, int, int, int], str, float]) -> None:
    """Запомнить прочитанное, только если настройку не писали, пока файл читали."""
    global _last
    with _swap:
        if _epoch == epoch:
            _last = now


def chosen_language() -> str:
    """Прочитать язык сейчас; битая настройка не превращает оформление в отказ.

    🔴 Вопрос о языке ходит по кругу, и круг замыкается здесь. Держатель языка живой
    (:func:`torrcast.domain.catalogs.tongue._follow_tongue`), поэтому каждая надпись
    спрашивает язык заново; язык лежит в настройке; а битую настройку
    :func:`~torrcast.adapters.filesystem.state.load_config.load_config` объявляет
    надписью из каталога (:func:`torrcast.domain.catalogs.phrase.phrase`) - и та снова
    спрашивает язык. ``except`` ниже до этого не доживал: рекурсия случалась при СБОРКЕ
    текста ошибки, то есть до броска, и упиралась в ``RecursionError`` вместо названной
    беды.

    Разрывается круг ровно тем, чего этой функции не хватало: знанием, что её позвали
    повторно из неё же самой. Повторный заход отвечает тем же умолчанием, каким она
    отвечает на нечитаемую настройку.

    🔴 Следствие названо вслух: настройка и есть единственный источник языка, поэтому
    при битой настройке жалоба выходит английской даже на русской установке. Второго
    источника языка тут не заводится (тот же выбор в
    :func:`torrcast.domain.catalogs.tongue._choose_tongue`).
    """
    if getattr(_asking, "busy", False):
        return EN
    _asking.busy = True
    try:
        path = config_path()
        now = time.monotonic()
        epoch, last = _epoch, _last
        if last is not None and last[0][0] == str(path) and now - last[2] < _GLANCE:
            return last[1]
        try:
            stat = os.stat(path)
            stamp = (str(path), stat.st_mtime_ns, stat.st_size, stat.st_ino)
        except OSError:
            return load_config().language
        language = last[1] if last is not None and last[0] == stamp else load_config().language
        _keep(epoch, (stamp, language, now))
        return language
    except TorrcastError:
        return EN
    finally:
        _asking.busy = False
