"""Инфохэш из магнита - устойчивое имя раздачи между двумя поисками."""

from __future__ import annotations

import re
from typing import Final

from torrcast.domain.release import Release

#: Значение ``xt`` в форме ``urn:btih:`` до следующего параметра. Длина не проверяется:
#: base32-форма магнита обязана дожить до сверки с таким же именем из прошлого поиска.
#: Разбор по ТОЧНОМУ hex-хэшу, который уезжает в TorrServer, - другое правило и другой
#: файл (:mod:`torrcast.domain.torrent_hash`).
#:
#: Ключ ищется точный и в нижнем регистре: у многосоставного магнита раздачи зовутся
#: ``xt.1``, ``xt.2`` и одной раздачей не являются. Двоеточия внутри ``urn:btih:`` берутся
#: и записанными как ``%3A``, а сам хэш читается как есть: hex и base32 состоят из знаков,
#: которые в адресе не кодируются.
_XT_BTIH: Final = re.compile(r"[?&]xt=(?i:urn(?::|%3A)btih(?::|%3A))([^&#]*)")


def info_hash(release: Release) -> str:
    """Инфохэш из магнита - устойчивое имя раздачи между двумя поисками."""
    found = _XT_BTIH.search(release.magnet)
    return found.group(1).lower() if found else ""
