"""Правило «оригинал раздачи называет другую работу той же франшизы»."""

from __future__ import annotations

import re
from typing import Final

from torrcast.domain.picture import Picture
from torrcast.domain.release import Release

#: Хвост оригинала, который работы не меняет: сезон, часть, номер, год.
_SAME_WORK_TAIL: Final = re.compile(
    r"^(?:\d{1,4}|\d+(?:st|nd|rd|th)|seasons?|part|cour|final|the|tv|i{1,3}|iv|vi{0,3}|ix|x)$"
)


def foreign_work(release: Release, picture: Picture) -> bool:
    """Оригинал раздачи продолжает оригинал картины словами другой работы.

    «Naruto: Shippuuden / Наруто [ТВ-2]» по-русски зовётся так же, как «Наруто» 2002 года,
    и склейка кладёт её в пул первого сериала; различает их только оригинал. Туда же
    «Rick and Morty: The Anime», «Shingeki no Kyojin OAD», «Naruto Specials».

    Хвост из слов сезона («Re:Zero kara Hajimeru Isekai Seikatsu 2nd», «The Final
    Season») работу не меняет. Оригинал, не продолжающий картину, а просто другой
    («Attack on Titan» при «Shingeki no Kyojin»), здесь не судится: это перевод имени.
    """
    mine, theirs = _words(picture.original), _words(release.original)
    if not mine or len(theirs) <= len(mine) or theirs[: len(mine)] != mine:
        return False
    return not all(_SAME_WORK_TAIL.match(word) for word in theirs[len(mine) :])


def _words(name: str | None) -> list[str]:
    return re.findall(r"\w+", (name or "").casefold())
