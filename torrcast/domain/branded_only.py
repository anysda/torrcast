"""Витрина вещателя вместо имени картины; зовёт разбор названий раздачи.

Латинская половина названия раздачи по умолчанию считается оригинальным именем картины,
и обычно так и есть. Но раздачи документалок пишут туда витрину канала: у
«BBC. Паразиты. Съеденные заживо. Змеи / BBC. Discovery channel exclusive (2002-2004)»
после косой черты стоит не имя картины, а строка продавца.

🔴 Пока такое «имя» никого не находило, оно было безвредно. Точное оригинальное имя
теперь несёт вес: под ним статья ищется прямой выборкой, и год перевыпуска сверяется
именно им (:func:`~torrcast.domain.facts.reissued.reissued`). Витрина, дошедшая до этого
места, однажды совпала бы с чужой статьёй точно - и человек прочитал бы под нашей
подписью чужую картинку.

Улика тут не имя канала само по себе: «The Discovery» - настоящее имя картины 2017 года,
а «Discovery Channel Exclusive» - нет. Улика - слово витрины, и рядом с ним не осталось
ничего своего.
"""

from __future__ import annotations

import re
from typing import Final

#: Вещатели, чьи имена стоят в названиях документальных раздач. Слова разбиты по одному:
#: «Nat Geo Wild» и «National Geographic» приходят и целиком, и кусками.
_BROADCASTERS: Final = frozenset(
    {
        "bbc",
        "discovery",
        "national",
        "geographic",
        "nat",
        "geo",
        "wild",
        "animal",
        "planet",
        "pbs",
        "nhk",
        "arte",
        "history",
        "netflix",
        "hbo",
    }
)
#: Слова витрины: ими называют канал и издание, но не картину. Хотя бы одно такое слово
#: обязано быть, иначе правило съело бы «The Discovery» и «Animal Planet» как имена.
_SHOWCASE: Final = frozenset(
    {"channel", "exclusive", "presents", "originals", "network", "edition"}
)
#: Слова, которые сами по себе не называют ничего и потому уликой не считаются.
_FILLER: Final = frozenset({"the", "a", "an", "tv", "hd", "uhd", "and"})
_WORD_RE: Final = re.compile("[0-9A-Za-z]+")


def _branded_only(part: str) -> bool:
    """Эта половина названия - витрина вещателя, а не имя картины."""
    words = [word.casefold() for word in _WORD_RE.findall(part)]
    if not any(word in _SHOWCASE for word in words):
        return False
    return all(word in _BROADCASTERS or word in _SHOWCASE or word in _FILLER for word in words)


__all__ = ["_branded_only"]
