"""Правило «раздача второй формы аниме другого года первого сезона картины не несёт»."""

from __future__ import annotations

import re
from typing import Final

from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release

#: Форма аниме «(ТВ-2)» при названии. Та же скобка после озвучки зовёт телеканал
#: («Dub (ТВ-3)», TC-985), и формой она не считается.
_LATER_FORM: Final = re.compile(
    r"(?<!\bdub)(?<![admp]vo)(?<!\bvo)(?<!\bsub)\s\((?:тв|tv)-[2-9]\)", re.IGNORECASE
)


def later_form(release: Release, picture: Picture, want: Episode) -> bool:
    """Раздача второй формы другого года: свой счёт серий, первого сезона картины в ней нет.

    «Синдром одиночки (ТВ-2) / … 2nd GIG [26 из 26] [2004]» склейка кладёт в картину 2002
    года, оригиналы разнятся сокращением («S.A.C.»), и s1e1 играл первую серию 2nd GIG.
    Год держит картину, которая сама и есть вторая форма.
    """
    years = (release.year, picture.year)
    if want.season != 1 or None in years or years[0] == years[1]:
        return False
    return _LATER_FORM.search(release.raw_name) is not None
