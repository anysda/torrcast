"""Чем подтверждённое разрешение хуже обещанного; зовёт отбраковка на стенде."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.media import Media
from torrcast.domain.rank_settings import HD_HEIGHT, HONEST_RATIO
from torrcast.domain.release import Release


def understated(release: Release, media: Media) -> str:
    """Чем подтверждённое разрешение хуже обещанного; пусто — релиз честен.

    Две половины, и обе взяты с живой выдачи «моаны 2»:

    1. имя называет разрешение, а внутри заметно меньше (:data:`HONEST_RATIO`);
    2. имя не называет ничего, а внутри не HD вовсе (:data:`HD_HEIGHT`) — это и есть
       верхний кандидат «Моаны 2»: ``WEB-DL-AVC`` без единой цифры в заголовке, 3.14 ГБ,
       140 сидов, а на деле 1150×574.

    И третья, про развёртку: имя обещает прогрессивный кадр, а поток чересстрочный
    (:attr:`~torrcast.domain.media.Media.interlaced`). Разрешение тут не врёт, поэтому
    высотой её не поймать - ловится только буквой.

    Возвращает кусок фразы, а не флаг: строка про подмену обязана назвать обе цифры,
    иначе она ничего не объясняет.
    """
    if not media.height:  # ffprobe высоту не отдал - сравнивать не с чем, молчим
        return ""
    if release.height:
        if media.frame < release.height * HONEST_RATIO:
            return phrase("rank.understated_named", named=release.quality, actual=media.quality)
        if media.interlaced and not release.interlaced:
            return phrase("rank.understated_named", named=release.quality, actual=media.quality)
        return ""
    if media.frame < HD_HEIGHT:
        return phrase("rank.understated_actual_only", actual=media.quality)
    return ""
