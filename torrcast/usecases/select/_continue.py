"""Продолжение по сохранённому выбору - путь, который обходится состоянием."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.usecases.playback._launch import _launch, _resume
from torrcast.usecases.select._about import _about
from torrcast.usecases.select._voiced import _Voiced, _voiced
from torrcast.usecases.start_clock import _Clock

if TYPE_CHECKING:
    from torrcast.domain.args import Args


def _continue(
    config: Config,
    key: str,
    entry: Entry,
    args: Args,
    clock: _Clock,
    *,
    launch: Callable[..., int] = _launch,
    resume: Callable[..., int] = _resume,
) -> int | None:
    """Продолжение по сохранённому выбору. ``None`` — состоянием не обойтись,
    дальше идёт обычный путь с поиском и меню.

    Ни сериал, ни фильм вопросов о продолжении не задают: релиз, дорожка, файл и
    позиция уже записаны.

    Названная в запросе серия - это запрос, а не ответ о месте: сериал ищет её в таблице
    своей же раздачи, а записи фильма ответить на неё нечем, и она уступает поиску.

    ``--voice`` поднимает раздачу ещё до показа (:func:`_revoice` читает её дорожки), и
    хозяин у неё — этот вызов, пока показ её не принял. Принимает он её ровно в одном
    случае: юнит поднялся и играет ТОТ ЖЕ магнит (:attr:`_Voiced.handed`) — дальше её
    уберёт сам юнит. Все прочие исходы — сухой прогон, Ctrl-C на вопросе, «серии тут нет»,
    не поднявшийся юнит — оставляли раздачу навсегда, и убирает
    её теперь ``finally``, по её собственному хэшу.

    Запуск показа и продолжение с места названы аргументами с боевым умолчанием: работа
    этой единицы - решить, какой из них зовут и с какой записью, и зеркалу надо мерить
    именно решение, а не показ, systemd и рой за каждым из них.
    """
    own = _Voiced()
    try:
        if not entry.serial:  # фильм (в том числе ошибочно записанный сериалом)
            if args.episode is not None:
                return None  # названа серия - фильму ответить на это нечем, ищем сериал
            if not entry.resumable:
                return None  # продолжать нечего - озвучку выберет обычный путь, по дорожкам
            entry = _voiced(config, entry, args, own)
            code = resume(config, key, entry, clock=clock, dry=args.dry)
            own.handed = not args.dry  # показ пошёл и раздача та же - дальше она его
            return code
        entry = _voiced(config, entry, args, own)
        if args.episode is not None:  # `cast киберпанк s2e5` - прыжок по кэшу раздачи
            jumped = entry.jump(args.episode.season, args.episode.episode)
            if jumped is None:
                return None  # серии в этой раздаче нет - честно идём искать релиз сезона
            code = launch(config, key, jumped, _about(jumped), clock, args.dry)
            own.handed = not args.dry
            return code
        if entry.done:  # конец раздачи: сама собой следующая серия не появится
            print(
                f"«{entry.title}» - {entry.label} была последней в раздаче, поэтому играю с начала"
            )
            first = entry.episodes[0]
            entry = entry.jump(first[0], first[1]) or entry
        code = launch(config, key, entry, _about(entry), clock, args.dry)
        own.handed = not args.dry
        return code
    finally:
        own.drop(config)
