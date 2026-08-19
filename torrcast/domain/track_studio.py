"""Определяет, чья озвучка играет на выбранной дорожке."""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.media import Media
from torrcast.domain.studio import Studio


def track_studio(media: Media, index: int, studios: Sequence[Studio] = ()) -> Studio | None:
    """Студия дорожки ``index``; ``None`` — не узнали, и гадать не станем.

    Сперва спрашиваем саму дорожку: её заголовок («MVO (LostFilm)») называет студию
    прямо, и точнее этого ответа нет.

    Дорожка молчит - остаётся имя раздачи (``studios``), и читается оно ПО ПОРЯДКУ:
    сезонный пак пишет «Dub (The Kitchen Russia) + MVO (Good People)» в том же
    порядке, в каком дорожки лежат в файле. Порядок этот - догадка, поэтому она
    обставлена условием: русских дорожек ровно столько же, сколько названо студий.
    Не сошлось - отвечаем «не узнали»: цена ошибки тут не «прежнее поведение», а
    запомненная чужая студия, то есть слышимая подмена на следующем сезоне.

    Нерусская дорожка студии не имеет вовсе: оригинал и чужой дубляж озвучкой в нашем
    смысле не являются.
    """
    if not 0 <= index < len(media.tracks):
        return None
    track = media.tracks[index]
    if (named := track.studio) is not None:
        return named
    if not track.is_russian:
        return None
    russian = [t.index for t in media.tracks if t.is_russian]
    if len(studios) != len(russian) or index not in russian:
        return None
    return studios[russian.index(index)]
