"""Сохранённое место переживает показ, который не поднялся: запись возвращается прежней.

Зовёт его запуск показа (:func:`torrcast.usecases.playback._launch._launch`) вокруг подъёма
юнита и ожидания картинки.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from torrcast.domain.entry import Entry
from torrcast.ports.show_unit.slot import unit as show_unit
from torrcast.ports.state_store.slot import store


@contextmanager
def place_kept(key: str, before: Entry | None, taken: Callable[[], bool]) -> Iterator[None]:
    """Не поднявшийся показ возвращает запись картины такой, какой нашёл её.

    🔴 Стартовая запись показа ложится под ключ картины ДО юнита - юнит читает из неё, что
    играть, - и до этой правки переживала любой исход. Отказ, таймаут, отмена человеком
    или чужой запуск оставляли в состоянии место, которого зритель не видел ни кадра:
    сериал, чей показ из веба не поднялся, дальше и в боте играл s1e1 с нуля (прод
    11-09-2026). Запись возвращается целиком: релиз, серия и позиция - одно место.

    Два случая оставляют запись как есть. Подъём снял чужой запуск (``taken``,
    :func:`torrcast.usecases.playback.launch_owner.taken_over`): состояние теперь пишет
    он, и откат затёр бы его запись. И юнит этой же картины жив - консоль прервали
    посреди ожидания, а показ поднялся и идёт: его место и есть настоящее.
    """
    try:
        yield
    except BaseException:
        if before is not None and not taken():
            _put_back(key, before)
        raise


def _put_back(key: str, before: Entry) -> None:
    unit = show_unit()
    if unit.active() and unit.key() == key:
        return
    state = store().load()
    state.put(key, before)
    store().save(state)
