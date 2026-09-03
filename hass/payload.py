"""Снимок показа как JSON для Home Assistant: только то, что снимок знает.

🔴 Чего в снимке нет, тут становится ``null``, а не удобным числом. Карточка плеера
рисует ровно эти поля, и выдуманная секунда или выдуманный номер серии - это враньё на
экране у зрителя, а не «дефолт».
"""

from __future__ import annotations

from hass.motion import IDLE, STARTING
from torrcast.domain.json_value import JsonValue
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.domain.split_episode import split_episode


def payload(
    shown: PlaybackSnapshot | None,
    *,
    version: str,
    tv: str,
    state: str,
    volume: float | None,
    disk_free: int,
    last_error: str,
    picture: tuple[str, str],
) -> dict[str, JsonValue]:
    """Снимок показа как тело ``GET /api/state``."""
    about = _about(shown) if state not in (IDLE, STARTING) else _nothing()
    return {
        "version": version,
        "tv": tv or None,
        "state": state,
        **about,
        # Адрес картинки на САМОМ серве, а не у Wikimedia: наружу за постером Home
        # Assistant не ходит ни при каких условиях (:data:`hass.posters.ROUTE`).
        # Отпечаток - ключ, которым он решает, тянуть ли картинку заново; без него
        # первая картинка прилипнет к карточке и переживёт смену показа.
        "image": picture[0] or None,
        "image_hash": picture[1] or None,
        "volume": volume,
        # Ноль тут не «диска нет», а отказ statvfs: каталог сегментов на живой машине
        # существует всегда (:meth:`torrcast.adapters.health.machine_probe.MachineProbe.disk_free`).
        "disk_free": disk_free or None,
        "last_error": last_error or None,
    }


def _nothing() -> dict[str, JsonValue]:
    """Про картину сказать нечего: показа нет, и прошлый снимок за него не отвечает."""
    return {
        "title": None,
        "shown_as": None,
        "season": None,
        "episode": None,
        "position": None,
        "duration": None,
        "warm": None,
    }


def _about(shown: PlaybackSnapshot | None) -> dict[str, JsonValue]:
    """Поля картины из снимка; пустого снимка на этих состояниях не бывает."""
    if shown is None:
        return _nothing()
    # Подпись собирается тем же порядком, каким её собирает цикл юнита для экрана:
    # имя картины и подпись серии (:mod:`torrcast.usecases.worker_loop`).
    shown_as = " ".join(filter(None, (shown.spoken, shown.label)))
    # Сезон и серия - из той же подписи, из которой их берёт человек. Разбирает её тот
    # же разбор, которым продукт читает «s1e3» из запроса; подписи нет - номеров нет.
    _, episode = split_episode(shown.label)
    return {
        "title": shown.spoken or None,
        "shown_as": shown_as or None,
        "season": episode.season if episode else None,
        "episode": episode.episode if episode else None,
        "position": round(shown.position, 1),
        "duration": round(shown.duration, 1) or None,
        "warm": _warm(shown),
    }


def _warm(shown: PlaybackSnapshot) -> JsonValue:
    """Прогрев процентом картины; длительности не знаем - не знаем и доли."""
    if shown.duration <= 0:
        return None
    return min(100, round(100 * shown.warm / shown.duration))
