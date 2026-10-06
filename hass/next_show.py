"""Переход на следующую серию: решение, завершать ли текущий показ.

Вкладка называет серию, которую ДОИГРАЛА (тело ``POST /api/next``): за секунды её
отсчёта сторож юнита показа мог доиграть сериал сам (:mod:`torrcast.usecases.worker`),
и тогда зов - не просьба, а повтор уже сделанного. Ответить на него новым запуском
значило бы перепрыгнуть серию и снять идущий показ (замер на живом приёмнике
10-09-2026: s1e2 кончилась во вкладке, запись уже была на s1e3, а переход поднял
s1e4 на телевизоре, оставив вкладку чёрной).

Нового запуска здесь нет: после решения мост завершает текущий показ штатной перемоткой.
Поэтому свойства HTTP-вкладки, в том числе её ключ, этому решению не нужны.
"""

from __future__ import annotations

from hass.following import following
from hass.refused_error import NO_NEXT, RefusedError
from torrcast.domain.json_value import JsonValue
from torrcast.ports.playback_session import PlaybackSession
from torrcast.ports.state_store.slot import store


def next_show(session: PlaybackSession, body: dict[str, JsonValue]) -> bool:
    """Разрешить штатно закончить серию; ``False`` - переход уже сделал её сторож.

    Тело без пары сезон/серия - старый зов (Home Assistant, стрелка в карточке): он
    идёт той же дорогой, что и всегда. Кривая пара - отказ тем же словом
    ``bad_episode``, каким её отвечает ``POST /api/play``
    (:func:`hass.play_extras.play_extras`).
    """
    season, episode = _ended(body)
    if season is not None and episode is not None and _moved_on(session, season, episode):
        return False
    if following(session) is None:
        raise RefusedError(NO_NEXT)
    return True


def _ended(body: dict[str, JsonValue]) -> tuple[int | None, int | None]:
    """Доигранная серия из тела зова; пустое тело - старый зов, пара ``(None, None)``."""
    season, episode = body.get("season"), body.get("episode")
    if season is None and episode is None:
        return None, None
    if not isinstance(season, int) or isinstance(season, bool) or season < 1:
        raise RefusedError("bad_episode")
    if not isinstance(episode, int) or isinstance(episode, bool) or episode < 1:
        raise RefusedError("bad_episode")
    return season, episode


def _moved_on(session: PlaybackSession, season: int, episode: int) -> bool:
    """Запись показа уже НЕ на доигранной серии: её доиграл сам сторож, зов запоздал."""
    if not session.active():
        return False
    entry = store().load().get(session.key())
    return entry is not None and (entry.season, entry.episode) != (season, episode)
