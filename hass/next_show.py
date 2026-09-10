"""Переход на следующую серию: решение, ЧТО запускать и запускать ли вообще.

Вкладка называет серию, которую ДОИГРАЛА (тело ``POST /api/next``): за секунды её
отсчёта сторож юнита показа мог доиграть сериал сам (:mod:`torrcast.usecases.worker`),
и тогда зов - не просьба, а повтор уже сделанного. Ответить на него новым запуском
значило бы перепрыгнуть серию и снять идущий показ (замер на стенде ``.104``
10-09-2026: s1e2 кончилась во вкладке, запись уже была на s1e3, а переход поднял
s1e4 на телевизоре, оставив вкладку чёрной).

Продолжение зовут туда же, где живёт показ: вкладке - с ``--here``, телевизору - как
всегда. Показу, отданному на ТВ кастом, вкладка не хозяин, и ``--here`` ему не положен.
"""

from __future__ import annotations

from hass.following import following
from hass.play_argv import play_argv
from hass.refused_error import RefusedError
from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.json_value import JsonValue
from torrcast.ports.playback_session import PlaybackSession
from torrcast.ports.state_store.slot import store
from torrcast.usecases.playback.hls_root import hls_root
from web.tv_session import SESSION


def next_show(session: PlaybackSession, body: dict[str, JsonValue]) -> list[str] | None:
    """argv запуска следующей серии; ``None`` - переход уже сделан, повторять нечего.

    Тело без пары сезон/серия - старый зов (Home Assistant, стрелка в карточке): он
    идёт той же дорогой, что и всегда. Кривая пара - отказ тем же словом
    ``bad_episode``, каким её отвечает ``POST /api/play``
    (:func:`hass.play_extras.play_extras`).
    """
    season, episode = _ended(body)
    if season is not None and episode is not None and _moved_on(session, season, episode):
        return None
    query = following(session)
    if query is None:
        # Слово «следующей нет» живёт у моста (:data:`hass.bridge.NO_NEXT`), который
        # зовёт эту функцию; импортировать его отсюда - кольцо, поэтому буквы повторены.
        raise RefusedError("no_next")
    return play_argv(query, None, None, None, None, False, _to_browser())


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


def _to_browser() -> bool:
    """Показ живёт во вкладке и не отдан на ТВ: продолжение играет у неё (``--here``).

    Ящик с ключом при ЖИВОМ касте тоже не пуст - каст из него и поднят, - но ему
    продолжение положено на телевизоре, как и шло: смена экрана на стыке серий была
    бы сюрпризом, а не продолжением.
    """
    if SESSION.active():
        return False
    return bool(read_web_box(hls_root(load_config().hls_dir)).get("key"))
