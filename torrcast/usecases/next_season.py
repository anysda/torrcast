"""Переход через границу сезона: раздача сезона доиграна - ищется следующий сезон.

Зовёт его цикл юнита (:func:`torrcast.usecases.worker_loop._worker_loop`) на стыке, где
запись уже сказала «досмотрено», а следующей серии в раздаче нет. Консоли на стыке нет,
поэтому каждый исход здесь - честная строка в ленту юнита, а не молчание. Раздача одной
серии соседей не знает вовсе: следующую ей называет каталог сериала, а находит тот же поиск.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from torrcast.domain.config import Config
from torrcast.domain.profile import Profile
from torrcast.ports.journal.slot import journal
from torrcast.ports.series_source import SeriesSource
from torrcast.ports.state_store.slot import store
from torrcast.ports.torrent_engine import TorrentEngine
from torrcast.usecases.discover.search_circle import search_circle
from torrcast.usecases.find_next import find_next
from torrcast.usecases.prepare_next import prepare_next as _prepare_next
from torrcast.usecases.prepared_next import PreparedNext
from torrcast.usecases.select_bench.bench import Bench
from torrcast.usecases.series_next import series_next

if TYPE_CHECKING:
    from torrcast.domain.entry import Entry
    from torrcast.usecases.select.plan import Plan

#: Каталог сериала, которым юнит называет серию за одиночной раздачей; кладёт его корень
#: (:mod:`torrcast.runtime.wire_show`). Без каталога одиночной серии продолжать нечем.
_series: SeriesSource | None = None


def _configure_next_season(series: SeriesSource) -> None:
    """Назначить юниту каталог сериала."""
    global _series
    _series = series


def _target(entry: Entry, series: SeriesSource | None) -> tuple[int, int] | None:
    """Что искать за краем раздачи: пак - следующий сезон, одна серия - серию по каталогу.

    Выход серии каталог тут не доказывает: доказывает его поиск раздачи ниже.
    """
    if entry.serial:
        return (entry.season + 1, 1) if entry.season is not None else None
    return series_next(entry, series) if series is not None else None


def _prepared_next(
    config: Config,
    key: str,
    torrserver: TorrentEngine,
    profile: Profile,
    entry: Entry,
    *,
    circle: Callable[..., list[Plan]] = search_circle,
    stand: Callable[..., Bench] = Bench,
    series: SeriesSource | None = None,
) -> PreparedNext | None:
    """Make one deferred search for a torrent boundary, without changing state yet."""
    if not entry.advance().done:
        return None
    target = _target(entry, series or _series)
    if target is None:
        return None
    return _prepare_next(config, key, torrserver, profile, entry, target, circle, stand)


def _next_season(
    config: Config,
    key: str,
    torrserver: TorrentEngine,
    profile: Profile,
    *,
    circle: Callable[..., list[Plan]] = search_circle,
    stand: Callable[..., Bench] = Bench,
    series: SeriesSource | None = None,
    prepared: PreparedNext | None = None,
) -> bool:
    """Досмотренный сезон - не конец сериала: найти и записать следующий, молча.

    🔴 TC-805. Конец сезонной раздачи и конец сезона для показа - одно событие
    (:meth:`torrcast.domain.entry.Entry.advance`), и раньше показ на нём просто вставал:
    зритель сидел перед погасшим экраном и звал следующий сезон руками. Теперь юнит ищет
    его сам, ровно одним кругом поиска: запрос - имя картины плюс ``s{N+1}e1``, та же
    форма, что у переспроса по сезону
    (:func:`torrcast.usecases.discover.season_reread.season_reread`).
    Нашёлся - запись следующей серии ложится в состояние, и цикл юнита играет её, как
    играл бы следующую серию внутри пака; озвучку новой раздачи решает память картины
    (:attr:`torrcast.domain.entry.Entry.voice` и ступень студии в отборе).

    ``False`` - продолжать нечего, и причина названа строкой: фильм и живая запись сюда
    не доходят вовсе, «сезона не нашлось» и «сезон есть, да играть нечем» - разные строки,
    потому что это разные правды для того, кто сидит перед экраном.

    Круг поиска и стенд отбора названы аргументами с боевым умолчанием: работа этой
    единицы - решение «искать следующий сезон или заканчивать показ», и зеркалу надо
    мерить именно его, а не Prowlarr и рой за ним.
    """
    entry = store().load().get(key)
    if entry is None or not entry.done or entry.season is None:
        return False  # не конец раздачи: фильм, стык внутри раздачи, живая запись
    if prepared is not None:
        following = prepared.result()
    else:
        target = _target(entry, series or _series)
        following = (
            find_next(config, key, torrserver, profile, entry, target, circle, stand)
            if target is not None
            else None
        )
    if following is None:
        return False
    next_entry, release = following
    state = store().load()
    state.put(key, next_entry)
    store().save(state)
    journal().emit(
        "select",
        "next_season",
        season=next_entry.season,
        episode=next_entry.episode,
        release=release,
    )
    return True
