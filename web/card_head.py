"""Голова показа греется с карточки: отбор кончился, раздача известна, клика ещё нет.

Карточка открыта, пока зритель читает её, и отбор (:mod:`web.voice_lookup`) кончается
раньше клика. Запись показа собирается той же :func:`_entry_of`, что у команды показа, и
тяжёлая голова ложится на полку под тем же ключом, под которым её спросит юнит
(:class:`torrcast.usecases.playback.head_ahead.HeadAhead`). Процесс один: клик по той же
раздаче вторую голову не заводит.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.tune import tune
from torrcast.ports.journal.slot import journal
from torrcast.ports.state_store.slot import store as watch_store
from torrcast.usecases.cast_command._entry_of import _entry_of
from torrcast.usecases.playback.head_ahead import HEAD

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.config import Config
    from torrcast.domain.profile import Profile
    from torrcast.ports.torrent_engine import TorrentEngine
    from torrcast.usecases.select._prep import _Prep
    from torrcast.usecases.select.plan import Plan


def card_head(
    config: Config, profile: Profile, engine: TorrentEngine, plan: Plan, prep: _Prep, args: Args
) -> None:
    """Завести голову раздачи, которую отбор карточки оставил греться."""
    try:
        state = watch_store().load()
        entry, _audio = _entry_of(state, state.find(args.title_query), plan, prep, args)
    except TorrcastError as exc:  # не собралась запись - клик заведёт голову сам
        journal().mark("голова с карточки не собралась", почему=type(exc).__name__)
        return
    HEAD.want(tune(config, profile), profile, engine, entry, owner=plan.picture.key)


__all__ = ["card_head"]
