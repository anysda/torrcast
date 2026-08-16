"""Определяет глубину цвета по паспорту видео."""

import re
from typing import Final

COPY_DEPTH = 8
_DEPTH_FMT: Final = re.compile("p(\\d{2,3})(?:[lb]e)?$")
_DEPTH_PROFILE: Final = re.compile("(?<!\\d)(\\d{1,2})(?!\\d)")


def color_depth(pix_fmt: str | None, profile: str | None = None) -> int:
    """Глубина цвета картинки в битах по паспорту ffprobe; молчит паспорт - :data:`COPY_DEPTH`.

    Спрашиваем сперва ``pix_fmt``, и это не вкусовщина: формат кадра - то, что видит
    декодер, а имя профиля пишет кодировщик, и оно бывает и пустым, и незнакомым
    (``High 10 Intra``, ``Hi10P`` в одних тулзах против ``High 10`` в ffprobe). Профиль
    остаётся вторым голосом ровно для случая, когда формата кадра в паспорте нет.

    Умолчание тут - именно 8, а не «неизвестно»: показ обязан на что-то решиться, и без
    единого признака десятибитности решаться он должен так же, как решался всегда -
    копией. Отличать «не спрашивали» от «спросили и там восемь» - дело не паспорта, а
    записи состояния (:attr:`torrcast.state.Entry.depth`).
    """
    if pix_fmt and (found := _DEPTH_FMT.search(pix_fmt.strip().casefold())):
        return int(found.group(1).lstrip("0") or COPY_DEPTH)
    if profile and (bits := _DEPTH_PROFILE.search(profile)):
        return max(COPY_DEPTH, int(bits.group(1)))
    return COPY_DEPTH
