"""Достаёт хэш раздачи прямо из магнита, не спрашивая TorrServer.
Читают его уборка своих раздач и сеанс показа для ``cast stop``.
"""

import base64
import re
from typing import Final

#: Хэш раздачи внутри магнита: сорок шестнадцатеричных знаков или тридцать два знака
#: base32, и ничего другого. TorrServer знает раздачу по hex, поэтому base32 переводится
#: в те же двадцать байт: это ТОЧНЫЙ хэш, а не похожая строка, и сносим мы только по нему.
_BTIH: Final = re.compile(r"xt=urn:btih:(?:([0-9a-fA-F]{40})|([A-Za-z2-7]{32}))(?![0-9A-Za-z])")


def _torrent_hash(magnet: str) -> str:
    """Хэш раздачи прямо из магнита, без похода в TorrServer; не разобрали — пусто.

    Нужен там, где хозяин раздачи уже умер и спросить у него нечего (``cast stop`` после
    убитого юнита): хэш - это часть самого магнита, и знать его можно, не поднимая ничего.
    """
    found = _BTIH.search(magnet)
    if not found:
        return ""
    hexed, based = found.groups()
    return hexed.lower() if hexed else base64.b32decode(based.upper()).hex()
