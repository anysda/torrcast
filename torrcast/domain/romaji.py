"""Правило romaji; используют модели и фасады разбора имён."""

from __future__ import annotations

import re
import unicodedata

from torrcast.domain._name_data.data_4 import _DOUBLED, _MORAS

_ALIEN = re.compile("[^а-яё \\-]")
_PARTS = re.compile("[ \\-]+")


def romaji(query: str) -> str:
    """Латиница запроса, если он сам уже японское имя кириллицей; иначе пустая строка.

    Разбор на моры и есть критерий. Японский слог берётся из закрытого набора, поэтому
    «каэдэ» и «судзу» на него раскладываются целиком, а русское слово спотыкается на
    первом же месте, которого в японском не бывает: стечение согласных («крики»), «ы»
    («колыма»), шипящая («нашего»), согласная на конце слова («супер», «дом»). Отвечать
    приходится по ЗАПРОСУ, а не по картине: справки на такое имя обычно нет вовсе, а
    первый круг кириллицей уже вернулся пустым.

    ⚠️ Критерий узкий намеренно, и цена ошибки у него односторонняя. Ложное «да» стоит
    одного лишнего круга по индексерам там, где и так ничего не нашлось; ложное «нет»
    оставляет всё как было - второго запроса просто не будет. Поэтому ряд «л» в таблицу
    не взят (в японском его нет, а в русских словах он на каждом шагу), и имя вроде
    «Гуррен Лаганн» этой правкой не берётся.

    Союз «и» - единственное русское слово, которое доезжает до сюда: остальное уже
    разобрано на моры. В японском имени на его месте стоит と, и подписаны раздачи именно
    так - `Kaede to Suzu`. Поэтому он переводится обратно, а не пишется буквой: буквой он
    режет выдачу источника с 19 строк до 2, а выброшенный вовсе - поднимает наверх чужую
    картину с нулём пиров, и показывать после него нечего.
    """
    lowered = unicodedata.normalize("NFKC", query).casefold().strip()
    if not lowered or _ALIEN.search(lowered):
        return ""
    said = []
    for word in _PARTS.split(lowered):
        if len(word) < 2:
            if word == "и":
                said.append("to")
            continue
        latin = _spell(word)
        if not latin:
            return ""
        said.append(latin)
    return " ".join(said)


def _spell(word: str) -> str:
    said: list[str] = []
    doubled = False
    at = 0
    while at < len(word):
        if not doubled and word[at] in _DOUBLED and word[at + 1 : at + 2] == word[at]:
            doubled = True
            at += 1
            continue
        size = next((n for n in (3, 2, 1) if word[at : at + n] in _MORAS), 0)
        if size:
            latin = _MORAS[word[at : at + size]]
        elif word[at] == "н":
            latin, size = "n", 1  # слоговая «н» стоит без гласной и на конце слова
        elif word[at] == "й" and said:
            latin, size = "i", 1  # хвост дифтонга: «кайсэн» - `kaisen`
        else:
            return ""
        said.append(latin[0] + latin if doubled else latin)
        doubled = False
        at += size
    return "" if doubled else "".join(said)


__all__ = ["romaji"]
