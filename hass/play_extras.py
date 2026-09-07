"""Разбор новых полей ``POST /api/play``: имя озвучки, серия и «сначала».

Старый вызов ``{query, pick}`` не называет ни одного из них, и обязан пройти этой же
дорогой без изменения смысла: отсутствующее поле - не отказ, а «взять умолчание»
:meth:`hass.bridge.Bridge.play`. Мост построит из результата тот же ``argv``, каким CLI
уже умеет читать ``--voice`` и серию ``sNeM`` - здесь только проверка входа.
"""

from __future__ import annotations

from typing import TypedDict

from torrcast.domain.json_value import JsonValue


class _PlayExtras(TypedDict, total=False):
    """Ровно те именованные доводы, что :meth:`hass.bridge.Bridge.play` берёт сверх пары
    ``query``/``pick`` - расходятся именами не более чем `**` умеет развернуть."""

    voice: str
    season: int
    episode: int
    from_start: bool
    here: bool


def play_extras(body: dict[str, JsonValue]) -> _PlayExtras | str:
    """Доводы показа поверх ``query``/``pick``, либо слово отказа."""
    voice = body.get("voice")
    if voice is not None and not isinstance(voice, str):
        return "bad_voice"
    season, episode = body.get("season"), body.get("episode")
    if not _clean_episode(season) or not _clean_episode(episode):
        return "bad_episode"
    if (season is None) != (episode is None):
        return "bad_episode"
    from_start = body.get("from_start", False)
    if not isinstance(from_start, bool):
        return "bad_from_start"
    # «here» - своя вкладка страницы просит показ себе (TC: «каста в браузер нет»), а не
    # на ``config.tv``. Молчание поля - это Home Assistant и бот, у них его не бывает
    # вовсе, и показ идёт на телевизор, как играл всегда.
    here = body.get("here", False)
    if not isinstance(here, bool):
        return "bad_here"
    extras: _PlayExtras = {"from_start": from_start, "here": here}
    if voice:
        extras["voice"] = voice
    if isinstance(season, int) and isinstance(episode, int):
        extras["season"], extras["episode"] = season, episode
    return extras


def _clean_episode(value: JsonValue) -> bool:
    """Пусто - можно, целое число от единицы - можно, всё остальное - отказ."""
    if value is None:
        return True
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1
