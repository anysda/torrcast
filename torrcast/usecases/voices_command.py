"""Отладочная ручка ``cast voices <запрос>``: какие озвучки есть у релиза для ТВ.
Зовёт её :func:`torrcast.cli.voices.voices`, показ отсюда не начинается.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeAlias

from torrcast.domain.config import Config
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.ports.progress import Progress
from torrcast.ports.progress import progress as progress_bar
from torrcast.ports.state_store import store as watch_store
from torrcast.ports.torrent_engines import TorrentEngines
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice._pick_plan import _pick_plan
from torrcast.usecases.discover.search_circle import search_circle
from torrcast.usecases.playback.file_picker import file_picker
from torrcast.usecases.rank._cut import _cut
from torrcast.usecases.rank.voices_table import voices_table
from torrcast.usecases.select._remembered import _remembered
from torrcast.usecases.select_bench.bench import Bench

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select.plan import Plan

    #: Чем ищется выдача: тот же круг поиска, что у показа (:func:`search_circle`), либо
    #: ответ подделки на стенде. Тип назван подписью самого поиска, а не свободным `Any`:
    #: меню зовёт его ровно этими тремя доводами и ждёт ровно планы картин.
    Search: TypeAlias = Callable[[Config, Args, Progress], list[Plan]]

#: Внешний мир меню озвучек: настройки, служба раздач и происхождение картины. Кладёт
#: их композиционный корень (:mod:`torrcast.runtime.wire`). Имена длиннее очевидных
#: нарочно: плоский namespace прежнего монолита (:mod:`torrcast.cli`) вписывает globals
#: каждой своей части в каждую другую, и короткий тёзка молча затирает функцию соседа.
_voices_settings: Callable[[], Config]
_voices_engines: TorrentEngines
_voices_native: Callable[[Picture, str], None]


def _configure_voices_command(
    settings: Callable[[], Config],
    engines: TorrentEngines,
    native: Callable[[Picture, str], None],
) -> None:
    """Назначить меню озвучек его внешний мир."""
    global _voices_settings, _voices_engines, _voices_native
    _voices_settings = settings
    _voices_engines = engines
    _voices_native = native


def _cmd_voices(args: Args, search: Search | None = None) -> int:
    """``cast voices <запрос>`` — какие озвучки есть у релиза, который поедет на ТВ.

    Отладочная ручка того же рода, что ``cast releases``: на счастливом пути озвучка
    выбирается сама, а посмотреть, из чего она выбрана, — сюда. Играть конкретную:
    ``cast <запрос> --voice N``.

    Показ отсюда не начинается и состояние не пишется; прогретые раздачи убираются из
    TorrServer, как и на всяком пути мимо показа (:meth:`Bench.drop_all`).
    """
    #: Чем искать. Умолчание боевое - тот же круг поиска, которым ищет показ; называет
    #: его тот, у кого своих служб нет: стенд и соседняя ручка ``cast releases``.
    search = search or search_circle
    config = _voices_settings()
    # Внутренний запрос той же формы, что пришёл: команда снимает с него своё слово
    # («voices») и играет остатком. Класс берётся у самого аргумента - разбор командной
    # строки живёт слоем выше, и сценарию его не назвать.
    inner = type(args)(
        query=list(args.query[1:]), release=args.release, pick=args.pick, file=args.file
    )
    if not inner.query:
        raise NotFoundError("что искать? cast voices <запрос>")
    with progress_bar() as progress:
        plans = search(config, inner, progress)
        bench = Bench(_voices_engines(config.torrserver_url), choose=file_picker(inner))
        try:
            plan = _pick_plan(plans, pick=inner.pick, asked=inner.title_query)
            _voices_native(plan.picture, inner.title_query)
            prep = bench.resolve(plan, inner, progress)
        finally:
            bench.drop_all()
    media = prep.found
    remembered = _remembered(watch_store().load(), plan.picture.key, None)
    print()
    print(f"{_named(plan.picture)} - релиз {prep.number}: {_cut(prep.release.title, 60)}")
    print(voices_table(media, media.default_track(), remembered))
    print()
    print("играть конкретную: cast <запрос> --voice N   (выбор запомнится на эту картину)")
    return EXIT_OK
