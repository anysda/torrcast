"""Честные строки о сериалах, выпавших из меню целиком: сезона нет, а раздачи есть."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.domain.seasons_named import seasons_named


def season_gaps(found: list[Picture], shown: set[str], want: Episode | None) -> list[str]:
    """Честные строки о сериалах, выпавших из меню целиком: сезона нет, а раздачи есть.

    🔴 Молчаливых отказов у нас не бывает, а тут был самый глухой из возможных: картина
    доезжает до меню живой, план по ней не строится (ни одна раздача не назвала нужный
    сезон - :meth:`~torrcast.domain.release.Release.covers`), и она просто исчезает из списка.
    Человек видит меню без неё и дефолт, вставший на соседа, - и ни одного слова о том,
    что произошло. Замер на «Гинтама»: картина 2018 года переживает привязку с 41
    раздачей и 33 живыми, на `s1e1` даёт ноль кандидатов, а дефолтом встаёт спин-офф
    «Gintama: 3-nen Z-gumi Ginpachi-sensei» - восьмым пунктом из восьми.

    Строка говорит ровно то, что мы знаем, и ни словом больше: сколько раздач у картины
    и какие сезоны они назвали. Обещать, что нужный сезон где-то есть, нельзя - его в
    этой выдаче действительно нет, и второй заход за ним уже сделан там, где он
    применим (:func:`_season_reinforce`).

    Молчат ли раздачи о сезонах вовсе (:func:`~torrcast.domain.seasons_named.seasons_named` пуста) -
    строки нет: сказать «сезона 1 нет» про имена, которые о сезонах не говорили,
    значило бы соврать. Такая картина в план и так попадает: молчание имени -
    «может быть», а не «нет».
    """
    asked = (want or Episode(1, 1)).season
    lines = []
    for picture in found:
        if picture.kind != "tv" or picture.key in shown or not picture.releases:
            continue
        if not (named := seasons_named(picture)):
            continue
        have = ", ".join(str(s) for s in named)
        lines.append(
            phrase(
                "discover.season_gap",
                title=picture.title,
                year=picture.year or "?",
                count=len(picture.releases),
                season=asked,
                seasons=have,
            )
        )
    return lines
