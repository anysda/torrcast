"""Продолжение по сохранённому выбору - путь, который обходится состоянием."""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.select._pick_state as _pick_state
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.usecases.playback._launch import _launch, _resume
from torrcast.usecases.select._about import _about
from torrcast.usecases.select._voiced import _Voiced, _voiced
from torrcast.usecases.start_clock import _Clock

if TYPE_CHECKING:
    from torrcast.ports.choice_types import Args


def _continue(config: Config, key: str, entry: Entry, args: Args, clock: _Clock) -> int | None:
    """Продолжение по сохранённому выбору. ``None`` — состоянием не обойтись,
    дальше идёт обычный путь с поиском и меню.

    Ни сериал, ни фильм вопросов о продолжении не задают: релиз, дорожка, файл и
    позиция уже записаны.

    ``--voice`` поднимает раздачу ещё до показа (:func:`_revoice` читает её дорожки), и
    хозяин у неё — этот вызов, пока показ её не принял. Принимает он её ровно в одном
    случае: юнит поднялся и играет ТОТ ЖЕ магнит (:attr:`_Voiced.handed`) — дальше её
    уберёт сам юнит. Все прочие исходы — сухой прогон, Ctrl-C на вопросе, «серии тут нет»,
    «смотреть сначала? нет», не поднявшийся юнит — оставляли раздачу навсегда, и убирает
    её теперь ``finally``, по её собственному хэшу.
    """
    own = _Voiced()
    try:
        if not entry.serial:  # фильм (в том числе ошибочно записанный сериалом)
            if not entry.resumable:
                return None  # продолжать нечего - озвучку выберет обычный путь, по дорожкам
            entry = _voiced(config, entry, args, own)
            code = _resume(config, key, entry, clock=clock, dry=args.dry)
            own.handed = not args.dry  # показ пошёл и раздача та же - дальше она его
            return code
        entry = _voiced(config, entry, args, own)
        if args.episode is not None:  # `cast киберпанк s2e5` - прыжок по кэшу раздачи
            jumped = entry.jump(args.episode.season, args.episode.episode)
            if jumped is None:
                return None  # серии в этой раздаче нет - честно идём искать релиз сезона
            code = _launch(config, key, jumped, _about(jumped), clock, args.dry)
            own.handed = not args.dry
            return code
        if entry.done:  # конец раздачи: сама собой следующая серия не появится
            print(f"«{entry.title}» - {entry.label} была последней в раздаче")
            if _pick_state._select_ask_line("Смотреть сначала? [Да/нет]")[:1] in {"н", "n"}:
                return EXIT_OK
            first = entry.episodes[0]
            entry = entry.jump(first[0], first[1]) or entry
        code = _launch(config, key, entry, _about(entry), clock, args.dry)
        own.handed = not args.dry
        return code
    finally:
        own.drop(config)
