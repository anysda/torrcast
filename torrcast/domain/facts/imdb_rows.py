"""Разбор выгрузок IMDb: рейтинги, голоса и карта русских прокатных имён.

Строки приносит адаптер (:mod:`torrcast.adapters.wiki.imdb_names`), а что в них значит
каждое поле и какая из одноимённых картин побеждает - решают правила отсюда.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Final

from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.patterns import _CYRILLIC
from torrcast.domain.facts.settings import SOURCE_MAP
from torrcast.domain.slugify import slugify

#: Типы записей IMDb, которые паспорт считает СЕРИАЛОМ: у сериала и фильма в выгрузке
#: разные строки, и подсказанный тип разводит однофамильцев так же, как тип статьи.
_TV_KINDS: Final = frozenset({"tvSeries", "tvMiniSeries"})
#: Разобранная карта имён: нормализованное имя → кандидаты
#: ``(tconst, тип, оригинал, год, имя как в выгрузке)``.
_RuName = tuple[str, str, str, str, str]

#: Латинские буквы, которыми выгрузка изредка подменяет похожие кириллические внутри
#: русского слова. Применяем только когда ВСЕ латинские буквы фрагмента входят в карту:
#: так ``B двyх`` чинится, а намеренные ``SuperПерцы``, ``COVID'а`` и римские цифры нет.
_RU_HOMOGLYPHS: Final = str.maketrans(
    "ABCEHKMOPTXYaceopxy",
    "АВСЕНКМОРТХУасеорху",
)


def _repair_ru_name(name: str) -> str:
    """Исправить латинские омоглифы внутри русского непробельного фрагмента."""

    russian_name = bool(_CYRILLIC.search(name))

    def repair(match: re.Match[str]) -> str:
        word = match.group()
        latin = [char for char in word if "A" <= char <= "Z" or "a" <= char <= "z"]
        mixed = bool(_CYRILLIC.search(word))
        # В выгрузке латинская B встречается и отдельным русским предлогом «В».
        if (
            latin
            and russian_name
            and (mixed or word == "B")
            and all(ord(char) in _RU_HOMOGLYPHS for char in latin)
        ):
            return word.translate(_RU_HOMOGLYPHS)
        return word

    return re.sub(r"\S+", repair, name)


def _ru_rows(lines: Iterable[str]) -> dict[str, list[_RuName]]:
    """Строки карты → словарь по нормализованному имени; битая карта равна отсутствующей."""
    out: dict[str, list[_RuName]] = {}
    try:
        for line in lines:
            fields = line.rstrip("\n").split("\t")
            name, tconst, kind, original, year = [*fields, "", "", "", "", ""][:5]
            if not name or not tconst:
                continue
            name = _repair_ru_name(name)
            candidates = out.setdefault(slugify(name), [])
            if all(tconst != known[0] for known in candidates):
                candidates.append((tconst, kind, original, year, name))
    except ValueError:  # битая карта равна отсутствующей
        pass
    return out


def _scores(lines: Iterable[str]) -> dict[str, str]:
    """Строки выгрузки рейтингов → ``tconst`` → оценка; шапка пропускается."""
    out: dict[str, str] = {}
    rows = iter(lines)
    next(rows, None)  # шапка «tconst averageRating numVotes»
    for line in rows:
        parts = line.split("\t")
        if len(parts) >= 2:
            out[parts[0]] = parts[1].strip()
    return out


def _vote_counts(lines: Iterable[str]) -> dict[str, int]:
    """Строки той же выгрузки → ``tconst`` → число голосов; битая равна отсутствующей."""
    out: dict[str, int] = {}
    try:
        rows = iter(lines)
        next(rows, None)  # шапка «tconst averageRating numVotes»
        for line in rows:
            parts = line.split("\t")
            if len(parts) >= 3 and parts[2].strip().isdigit():
                out[parts[0]] = int(parts[2])
    except ValueError:
        pass
    return out


def _named_origin(
    candidates: list[_RuName], series: bool, votes: Callable[[], dict[str, int]]
) -> Origin:
    """Кандидаты карты под спрошенный тип → паспорт; выбор из нескольких - догадка.

    Ручательство тут - САМА пара «имя - картина» из выгрузки: это утверждение каталога, а
    не сходство строк, поэтому единственный кандидат догадкой не считается. Несколько
    картин под одним именем - другое дело: выбор между ними делает число голосов IMDb, а
    это уже чья-то оценка, поэтому такой паспорт помечается ``guessed`` - решает гейт
    добора. Голосов нет (файл не доехал) - молчим: неподтверждённый выбор хуже пустого.

    Оригинал на кириллице (русская картина) латинским именем не является: добирать ей
    нечем, и ``title`` честно остаётся пустым - а вот год отдаём, он опора гейта.
    """
    typed = [candidate for candidate in candidates if (candidate[1] in _TV_KINDS) == series]
    if not typed:
        return Origin()
    guessed = False
    if len(typed) > 1:
        counted = votes()
        best = max(typed, key=lambda candidate: counted.get(candidate[0], 0))
        if not counted.get(best[0]):
            return Origin()
        typed = [best]
        guessed = True
    _tconst, _kind, original, raw_year, name = typed[0]
    year = int(raw_year) if raw_year.isdigit() else None
    latin = "" if _CYRILLIC.search(original) else original
    return Origin(title=latin, year=year, name=name, guessed=guessed, source=SOURCE_MAP)
