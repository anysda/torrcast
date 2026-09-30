"""Голова показа греется с карточки: отбор кончился, раздача известна, клика ещё нет.

Карточка открыта, пока зритель читает её, и отбор (:mod:`web.voice_lookup`) кончается
раньше клика. Запись показа собирается той же :func:`_entry_of`, что у команды показа, и
тяжёлая голова ложится на полку под тем же ключом, под которым её спросит юнит
(:class:`torrcast.usecases.playback.head_ahead.HeadAhead`). Процесс один: клик по той же
раздаче вторую голову не заводит.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from torrcast.domain.magnet_hash import magnet_hash
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.tune import tune
from torrcast.ports.journal.slot import journal
from torrcast.ports.state_store.slot import store as watch_store
from torrcast.usecases.cast_command._entry_of import _entry_of
from torrcast.usecases.playback.head_ahead import HEAD

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.config import Config
    from torrcast.domain.entry import Entry
    from torrcast.domain.profile import Profile
    from torrcast.ports.torrent_engine import TorrentEngine
    from torrcast.usecases.select._prep import _Prep
    from torrcast.usecases.select.plan import Plan


def card_head(
    config: Config,
    profile: Profile,
    engine: TorrentEngine,
    plan: Plan,
    prep: _Prep,
    args: Args,
    kept: Entry | None = None,
) -> None:
    """Завести голову раздачи, которую отбор карточки оставил греться.

    ``kept`` - закладка, которую продолжит «Играть» (:meth:`WatchState.bookmark_key`): показ
    получит её запись как есть, и голова ложится по ней, с её места и дорожки, под тем же
    ключом полки. Запись по выбору отбора качала бы и резала раздачу, которую не сыграют.
    """
    try:
        if kept is not None:
            entry = kept
        else:
            state = watch_store().load()
            entry, _audio = _entry_of(state, state.find(args.title_query), plan, prep, args)
    except TorrcastError as exc:  # не собралась запись - клик заведёт голову сам
        journal().mark("голова с карточки не собралась", почему=type(exc).__name__)
        return
    HEAD.want(
        tune(config, profile), profile, engine, entry, owner=plan.picture.key, late=_shown(entry)
    )


def _shown(entry: Entry) -> Callable[[], bool]:
    """Показ этой раздачи уже поднят: клик пришёл раньше, чем голова карточки спланирована.

    Отметку показа ставит юнит, подняв раздачу (:meth:`WatchState.showing`), и свою
    голову показ тогда кодирует сам - вторая рядом делила бы с ним ядра.
    """
    torrent = magnet_hash(entry.magnet)

    def late() -> bool:
        live = watch_store().load().showing()
        return live is not None and magnet_hash(live[1].magnet) == torrent

    return late


__all__ = ["card_head"]
