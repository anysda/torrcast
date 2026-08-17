"""Одна строка сырой выдачи индексера: имя, хэш, размер, сиды и кто её принёс."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final, TypeAlias

from torrcast.adapters.prowlarr.magnet_for import magnet_for

_HASH_RE: Final = re.compile(r"^[0-9a-fA-F]{40}$")
#: Сырые поля одной строки выдачи в порядке :meth:`RawResult.build`.
Row: TypeAlias = tuple[Any, Any, Any, Any, Any]


@dataclass(frozen=True, slots=True)
class RawResult:
    """Раздача, как её назвал каталог: до разбора имени и до всякого отбора."""

    title: str
    info_hash: str
    size: int = 0
    seeders: int = 0
    indexer: str = ""
    #: Сколькими строками выдачи приехала эта раздача: индексеры зеркалят друг друга, и
    #: один торрент приходит от нескольких сразу. Склейка оставляет одну строку, но
    #: помнит, сколько их было - иначе счёт «сколько нашлось» зависел бы от того, как
    #: устроен опрос индексеров, а не от каталога.
    copies: int = 1
    #: ВСЕ индексеры, принёсшие эту раздачу, по именам и по алфавиту. Склейка оставляет
    #: одну строку, и поле :attr:`indexer` у неё - индексер той строки, чьё ИМЯ победило,
    #: а не «откуда раздача вообще пришла». Разница не бухгалтерская: у Nyaa и AniLibria
    #: аниме - всё, что там лежит, и признак жанра
    #: (:attr:`~torrcast.domain.release.Release.anime`) читается именно отсюда. Пусто -
    #: строка ещё не проходила склейку, и всё, что известно, стоит в :attr:`indexer`.
    indexers: tuple[str, ...] = ()
    #: ВСЕ имена, под которыми приехала эта раздача, по алфавиту. Склейка выбирает имя
    #: большинством, а признаки имени - например, метку внешней дорожки
    #: (:attr:`~torrcast.domain.release.Release.external_dub`) - читают отсюда: то, что
    #: сказал каталог об одной и той же раздаче, складывается, а не выбирается вместе с
    #: именем победителя. Пусто - строка ещё не проходила склейку, и всё, что известно,
    #: стоит в :attr:`title`.
    names: tuple[str, ...] = ()

    @property
    def magnet(self) -> str:
        return magnet_for(self.info_hash, self.title)

    @classmethod
    def build(cls, title: Any, info_hash: Any, size: Any, seeders: Any, indexer: Any) -> RawResult:
        """Собрать результат из сырых полей; без валидного hash строка бесполезна."""
        text = str(info_hash or "").strip()
        if not _HASH_RE.match(text) or not str(title or "").strip():
            raise ValueError("нет hash или имени")
        return cls(str(title), text, _int(size), _int(seeders), str(indexer or ""))

    @classmethod
    def collect(cls, rows: Iterable[Row]) -> list[RawResult]:
        """Собрать строки выдачи, молча пропуская непригодные (без hash или имени)."""
        out: list[RawResult] = []
        for row in rows:
            try:
                out.append(cls.build(*row))
            except ValueError:
                continue
        return out


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


__all__ = ["RawResult", "Row"]
