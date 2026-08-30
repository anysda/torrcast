"""Надпись по ключу на языке человека, со значениями, подставленными по имени.

Каталоги распределены по кластерам продукта: у каждого кластера своя пара файлов
``ru.py`` / ``en.py``, и растёт список кластеров, а не один файл на весь продукт.
Английский тут одновременно язык по умолчанию и запасной каталог: ключ, которого в
русском ещё нет, отвечает по-английски, а не пустотой и не ключом.
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.catalogs.choice.en import en as choice_en
from torrcast.domain.catalogs.choice.ru import ru as choice_ru
from torrcast.domain.catalogs.digest.en import en as digest_en
from torrcast.domain.catalogs.digest.ru import ru as digest_ru
from torrcast.domain.catalogs.discover.en import en as discover_en
from torrcast.domain.catalogs.discover.ru import ru as discover_ru
from torrcast.domain.catalogs.frames.en import en as frames_en
from torrcast.domain.catalogs.frames.ru import ru as frames_ru
from torrcast.domain.catalogs.health.en import en as health_en
from torrcast.domain.catalogs.health.ru import ru as health_ru
from torrcast.domain.catalogs.rank.en import en as rank_en
from torrcast.domain.catalogs.rank.ru import ru as rank_ru
from torrcast.domain.catalogs.select.en import en as select_en
from torrcast.domain.catalogs.select.ru import ru as select_ru
from torrcast.domain.catalogs.select_bench.en import en as select_bench_en
from torrcast.domain.catalogs.select_bench.ru import ru as select_bench_ru
from torrcast.domain.catalogs.tongue import RU, tongue

#: Кластеры каталога: (английский, русский). Заход перевода добавляет сюда строку -
#: пару файлов своего кластера, - а не правит эту функцию. Строка на кластер и запятая
#: в конце: так соседний заход добавляет свой кластер, не трогая ничьей чужой строки.
_CLUSTERS: Final = (
    (choice_en, choice_ru),
    (digest_en, digest_ru),
    (discover_en, discover_ru),
    (frames_en, frames_ru),
    (health_en, health_ru),
    (rank_en, rank_ru),
    (select_bench_en, select_bench_ru),
    (select_en, select_ru),
)


def phrase(key: str, **values: object) -> str:
    """Собрать надпись: ключ + значения по имени, на языке из :func:`tongue`."""
    english: dict[str, str] = {}
    spoken: dict[str, str] = {}
    for in_english, in_russian in _CLUSTERS:
        english.update(in_english())
        spoken.update(in_russian() if tongue() == RU else in_english())
    return spoken.get(key, english[key]).format(**values)
