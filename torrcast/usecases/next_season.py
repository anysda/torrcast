"""Переход через границу сезона: раздача сезона доиграна - ищется следующий сезон.

Зовёт его цикл юнита (:func:`torrcast.usecases.worker_loop._worker_loop`) на стыке, где
запись уже сказала «досмотрено», а следующей серии в раздаче нет. Консоли на стыке нет,
поэтому каждый исход здесь - честная строка в ленту юнита, а не молчание. Раздача одной
серии соседей не знает вовсе: следующую ей называет каталог сериала, а находит тот же поиск.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from torrcast.domain.args import Args
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.profile import Profile
from torrcast.domain.slugify import slugify
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.journal.slot import journal
from torrcast.ports.progress.slot import progress as progress_bar
from torrcast.ports.series_source import SeriesSource
from torrcast.ports.state_store.slot import store
from torrcast.ports.torrent_engine import TorrentEngine
from torrcast.usecases.cast_command._entry_for import _entry_for
from torrcast.usecases.discover.search_circle import search_circle
from torrcast.usecases.playback.file_picker import file_picker
from torrcast.usecases.rank.pick_voice import pick_voice
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


def _next_season(
    config: Config,
    key: str,
    torrserver: TorrentEngine,
    profile: Profile,
    *,
    circle: Callable[..., list[Plan]] = search_circle,
    stand: Callable[..., Bench] = Bench,
    series: SeriesSource | None = None,
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
    target = _target(entry, series or _series)
    if target is None:
        return False  # одна серия вне каталога или последняя в нём
    season, (upcoming, episode) = entry.season, target
    # Серия того же сезона - не «сезон досмотрен»: строк про сезон тут не говорится.
    same = upcoming == season
    words = (entry.query or slugify(entry.title)).replace("-", " ").split()
    args = Args(query=[*words, f"s{upcoming}e{episode}"])
    if not same:
        print(
            phrase("season.searching_next", title=entry.spoken, season=season, upcoming=upcoming),
            flush=True,
        )
    journal().mark("поиск следующего сезона", сезон=upcoming, серия=episode)
    with progress_bar() as progress:
        try:
            plans = circle(config, args, progress, profile)
        except NotFoundError as err:
            # Выдача без серии - ответ каталога, а не сбой поиска.
            word = "season.no_releases_found" if same else "season.no_next_found"
            print(
                phrase(word, title=entry.spoken, season=season, upcoming=upcoming, err=err),
                flush=True,
            )
            return False
        except TorrcastError as err:
            # Поиск не состоялся (индексеры, сеть): «последний» здесь было бы ложью.
            print(
                phrase("season.search_failed", title=entry.spoken, upcoming=upcoming, err=err),
                flush=True,
            )
            return False
        plan = next((p for p in plans if p.picture.key == key), None)
        if plan is None:
            said = phrase(
                "season.no_releases_found", title=entry.spoken, season=season, upcoming=upcoming
            )
            print(said, flush=True)
            return False
        bench = stand(torrserver, choose=file_picker(args), profile=profile)
        try:
            prep = bench.resolve(plan, args, progress)
        except TorrcastError as err:
            bench.drop_all()  # прогретое без показа - мусор в рое
            # Сезон есть, но играть его нечем: отказ отбора называет причину сам.
            print(
                phrase("season.could_not_start", title=entry.spoken, upcoming=upcoming, err=err),
                flush=True,
            )
            return False
        bench.keep_only(prep)  # взятую раздачу с этой секунды держит показ, не стенд
        audio, voice = pick_voice(
            prep.found, args, entry.voice, plan.picture.native, prep.release.studios
        )
        # Память студии переезжает через границу сезона вместе с памятью дорожки: у
        # новой раздачи запомненной студии может не быть вовсе, и тогда играется что
        # есть, а помнится прежнее (:attr:`torrcast.domain._playing._Playing.studio`).
        # Подмену зритель прочтёт на экране подписью показа (:func:`voice_swap`).
        following = _entry_for(
            plan, prep, prep.release, prep.want, prep.found, audio, voice, entry.studio, args
        )
    state = store().load()
    state.put(key, following)
    store().save(state)
    journal().emit("select", "next_season", season=upcoming, episode=episode, release=prep.number)
    return True
