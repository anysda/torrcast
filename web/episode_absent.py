"""Вышедшая серия, которой нет ни в одной раздаче: приговор приезжает ПОЗЖЕ карточки.

Список серий сериала карточка берёт из каталога (:mod:`web.series_catalog`), а каталог
знает эфир, а не трекеры: в свежем сезоне есть вышедшие серии, которых сейчас нет ни в
одной раздаче. Узнать это можно только перебором раздач, а свои файлы раздача называет
только через TorrServer (:class:`web.episode_lookup.EpisodeLookup`) - секунды роя на
каждую. Перебор внутри ответа сломал бы обещанные карточке 2 с (TC-1250), поэтому строка
сначала обычная и НАЖИМАЕТСЯ, а гаснет позже, когда перебор договорил: ответ приезжает
тем же путём, что и дорожки (``voices_pending``) - телом следующего добора.

🔴 Третьего состояния не избежать. Булево «есть/нет» превратило бы молчание TorrServer
или раздачу без нумерации в приговор «серии нет», а погашенная по ошибке строка - это
отнятый у зрителя показ. Приговор выносится, только когда КАЖДАЯ раздача, способная
держать серию, сказала своё слово; всё остальное - «не знаю», и строка остаётся живой.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from time import monotonic
from typing import Final, Protocol

from torrcast.domain.json_value import JsonValue
from torrcast.domain.release import Release
from web.episode_lookup import UNAVAILABLE

#: Сколько разборов раздач заводить за один ответ карточки. Каждый разбор - это добавление
#: раздачи в TorrServer и ожидание роя, и веер на весь пул положил бы и рой, и саму
#: машину показа. Пул проходится волнами: следующий добор страницы заводит следующие.
WAVE: Final = 4
#: Сколько карточка вообще держит сезон «в поиске». Это общий предел волнового перебора:
#: даже чужая реализация таблиц, вечно отвечающая ``None``, страницу не удержит.
HUNT: Final = 90.0


class _EpisodeTables(Protocol):
    """Кэш таблиц серий, достаточный приговору (:class:`web.episode_lookup.EpisodeLookup`)."""

    def table(self, release: Release, base_url: str) -> list[list[int]] | None: ...


@dataclass
class EpisodeAbsent:
    """Приговор «серии нет ни в одной раздаче» по сезону открытой вкладки.

    Помнит только, когда по сезону начался перебор: сами таблицы раздач лежат в кэше
    разбора, один на процесс. Часы подставные ради тестов.
    """

    clock: Callable[[], float] = monotonic
    _since: dict[tuple[str, int], float] = field(default_factory=dict)

    def of(
        self,
        rows: list[JsonValue],
        key: str,
        season: int,
        releases: Sequence[Release],
        episodes: _EpisodeTables,
        base_url: str,
        saved: Mapping[int, list[JsonValue]] | None = None,
        ordinal: bool = False,
    ) -> tuple[list[JsonValue], bool]:
        """Строки сезона с пометкой погашенных и «перебор ещё идёт».

        ``saved`` - строки закладки: их приговор не трогает. Закладка знает серию ПО
        ФАЙЛАМ своей раздачи, и её саму показ играет даже вне пула
        (:func:`web.card_seasons._bookmark_release`, TC-1263). Гасить такую строку
        значило бы отнять у зрителя ровно то, что он уже открывал.

        ``ordinal`` - список чужой раздачам нумерации («Интерны» IMDb 60, 60, 61, 98):
        номер строки там сквозной, и таблицы раздач о нём ничего не знают. Приговор по
        такому списку был бы приговором по чужим числам, и его не выносят вовсе.
        """
        aired = _aired(_season_row(rows, season), _spared(saved, season))
        if ordinal or not aired:
            return rows, False
        gone, hunting = self._gone(aired, season, releases, episodes, base_url)
        marked = _marked(rows, season, gone) if gone else rows
        return marked, hunting and self._left(key, season)

    def _gone(
        self,
        aired: list[int],
        season: int,
        releases: Sequence[Release],
        episodes: _EpisodeTables,
        base_url: str,
    ) -> tuple[list[int], bool]:
        """Серии, которых нет ни в одной раздаче, и «часть раздач ещё не ответила».

        Сезон, которого не покрывает ни одна раздача, гаснет сразу: это видно по ИМЕНАМ
        раздач, без сети и без перебора. Дальше имена отвечают за раздачи, называющие
        свои серии, а за паки отвечают только их файлы.
        """
        covering = [release for release in releases if release.covers(season)]
        if not covering:
            return aired, False
        named = {number for release in covering for number in _named(release)}
        left = [number for number in aired if number not in named]
        unknown = 0
        unavailable = False
        for release in covering:
            if not left or unknown >= WAVE:
                break
            if _named(release):
                continue
            table = episodes.table(release, base_url)
            if table is None:
                unknown += 1  # разбор в пути или упал: раздача ещё ничего не сказала
                continue
            if table is UNAVAILABLE:
                unavailable = True
                continue
            if not table:
                return [], False  # раздача без нумерации: «серий нет» она не знает
            left = [number for number in left if not _holds(table, season, number)]
        if unknown:
            return [], True
        return ([], False) if unavailable else (left, False)

    def _left(self, key: str, season: int) -> bool:
        """Ещё ищем или уже сдались: перебор не держит страницу дольше :data:`HUNT`."""
        now = self.clock()
        return now - self._since.setdefault((key, season), now) < HUNT


def _season_row(rows: list[JsonValue], season: int) -> dict[str, JsonValue] | None:
    for row in rows:
        if isinstance(row, dict) and row.get("n") == season:
            return row
    return None


def _spared(saved: Mapping[int, list[JsonValue]] | None, season: int) -> set[int]:
    """Номера строк закладки: их приговор не трогает."""
    spared = set()
    for row in saved.get(season, []) if saved else []:
        number = row.get("n") if isinstance(row, dict) else None
        if isinstance(number, int):
            spared.add(number)
    return spared


def _aired(row: dict[str, JsonValue] | None, spared: set[int]) -> list[int]:
    """Номера вышедших серий сезона, за которые отвечает пул раздач.

    Строка с ``air`` ещё не вышла - её гасит своё правило и своя дата. Просмотренную и
    начатую строку держит закладка, а её раздачи в пуле может не быть вовсе.
    """
    episodes = row.get("episodes") if row is not None else None
    if not isinstance(episodes, list):
        return []
    aired = []
    for cell in episodes:
        if not isinstance(cell, dict) or cell.get("air") or cell.get("watched"):
            continue
        number = cell.get("n")
        if isinstance(number, int) and number not in spared and not cell.get("pos"):
            aired.append(number)
    return aired


def _named(release: Release) -> tuple[int, ...]:
    """Серии, НАЗВАННЫЕ именем раздачи; пусто - имя о сериях молчит, и это пак."""
    if release.episodes:
        return release.episodes
    return (release.episode,) if release.episode is not None else ()


def _holds(table: list[list[int]], season: int, number: int) -> bool:
    return any(len(row) > 1 and row[0] == season and row[1] == number for row in table)


def _marked(rows: list[JsonValue], season: int, gone: list[int]) -> list[JsonValue]:
    absent: list[JsonValue] = [*gone]
    return [
        {**row, "absent": absent} if isinstance(row, dict) and row.get("n") == season else row
        for row in rows
    ]


#: Приговор боевого пути: часы настоящие, память о переборе - на процесс.
ABSENT: Final = EpisodeAbsent()


__all__ = ["ABSENT", "HUNT", "WAVE", "EpisodeAbsent"]
