"""Надпись по ключу на языке человека, со значениями, подставленными по имени.

Каталоги распределены по кластерам продукта: у каждого кластера своя пара файлов
``ru.py`` / ``en.py`` в своей папке рядом. Список кластеров этот файл не хранит -
он собирает его обходом соседних папок (:func:`_clusters`), один раз при импорте.
Заход перевода заводит только папку своего кластера и не правит тут ни строки: без
этого каждый новый кластер придвигал бы файл к потолку длины чужим по смыслу кодом
(структурный сторож меряет длину строго этого файла, а не всего каталога).
Английский тут одновременно язык по умолчанию и запасной каталог: ключ, которого в
русском ещё нет, отвечает по-английски, а не пустотой и не ключом.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Final

from torrcast.domain.catalogs.tongue import RU, tongue

#: Каталог кластера: без аргументов, отдаёт ключ -> шаблон.
_Side = Callable[[], dict[str, str]]


def _cluster_pair(name: str) -> tuple[_Side, _Side]:
    """Импортировать `en.py`/`ru.py` кластера `name` и вернуть его каталоги.

    Импорт по строке, собранной из имени папки, - единственный честный способ
    подшить кластер, найденный обходом каталога, а не перечисленный тут поимённо.
    Гейт знает про этот вызов поимённо (`scripts/structure_gate.py`,
    `NAMED_EXCEPTIONS`), а поиск мёртвого кода - отдельно (`scripts/dead_code.py`,
    `roots`), чтобы обход каталога не читался у него мёртвым импортом.
    """
    package = f"torrcast.domain.catalogs.{name}"
    english_module = importlib.import_module(f"{package}.en")
    russian_module = importlib.import_module(f"{package}.ru")
    english: _Side = english_module.en
    russian: _Side = russian_module.ru
    return english, russian


def _clusters() -> tuple[tuple[_Side, _Side], ...]:
    """Собрать кластеры обходом соседних папок: у каждой свои `en.py` и `ru.py`."""
    root = Path(__file__).parent
    names = sorted(
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and (entry / "en.py").is_file() and (entry / "ru.py").is_file()
    )
    return tuple(_cluster_pair(name) for name in names)


#: Кластеры каталога, собранные один раз при импорте модуля: смотри :func:`_clusters`.
_CLUSTERS: Final = _clusters()


def phrase(key: str, **values: object) -> str:
    """Собрать надпись: ключ + значения по имени, на языке из :func:`tongue`."""
    english: dict[str, str] = {}
    spoken: dict[str, str] = {}
    for in_english, in_russian in _CLUSTERS:
        english.update(in_english())
        spoken.update(in_russian() if tongue() == RU else in_english())
    return spoken.get(key, english[key]).format(**values)
