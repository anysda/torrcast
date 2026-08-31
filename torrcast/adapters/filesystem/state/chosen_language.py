"""Свежий язык продукта из настройки, с безопасным английским умолчанием."""

from __future__ import annotations

import threading

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.catalogs.tongue import EN
from torrcast.domain.torrcast_error import TorrcastError

#: Спрашивает ли ЭТОТ поток язык прямо сейчас. Флаг потоко-честный, потому что у
#: продукта есть щупы роя (:mod:`torrcast.usecases.select_bench._bench_work`): общий
#: на процесс флаг гасил бы язык соседу - пока один поток читает настройку, второй
#: получал бы английский на живой и вполне читаемой русской установке.
_asking = threading.local()


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
        return load_config().language
    except TorrcastError:
        return EN
    finally:
        _asking.busy = False
