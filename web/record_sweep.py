"""Раздачи истории за первыми записями ряда «Продолжить» не лежат в базе TorrServer.

Держатель (:mod:`web.record_hold`) паркует только первые
:data:`~torrcast.domain.continue_row.WARM_ROW` записей ряда: их кэш на диске ждёт клика.
Раздача записи, выпавшей из первых, и раздача, закрытая без сноса прошлой сборкой или
прерванной уборкой, держали бы 40-200 МБ кэша навсегда, поэтому они сносятся (``rem``).
Реестр - сама база службы, сверенная с историей: он переживает рестарт и не теряет
раздачу, о которой процесс не успел записать. Фоном сверку зовут касание ряда и старт
службы (:mod:`web.sweep_later`). Сносятся только точные хэши из магнитов истории: чужие
раздачи службы (поиск, отбор, показ) тут не видны.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from torrcast.domain.continue_row import WARM_ROW, continue_row
from torrcast.domain.entry import Entry
from torrcast.domain.torrent_hash import _torrent_hash
from torrcast.usecases.torrent_claims import CLAIMS


class _Listing(Protocol):
    """Служба, у которой спрашивают её базу и сносят из неё раздачу вместе с кэшем."""

    def hashes(self) -> set[str]: ...

    def drop(self, torrent_hash: str) -> bool: ...


def record_sweep(
    engine: _Listing, entries: Mapping[str, Entry], spared: Callable[[str], bool]
) -> tuple[list[str], bool]:
    """Снести из базы службы раздачи истории вне первых записей ряда; что снесено и всё ли.

    ``spared`` - раздача занята сейчас: её держит показ, отбор или страница
    (:func:`torrcast.usecases.torrents._held_by_show`). Отпустит держатель - снесёт он сам.
    Спрашивается и сносится под замком отметок
    (:meth:`~torrcast.usecases.torrent_claims.TorrentClaims.dropping`): держатель, заводящий
    раздачу в ту же секунду, её не потеряет.

    Сетевой ``rem`` идёт под этим замком, поэтому проход обрывается, когда служба снос не
    приняла или держатель ждал замка
    (:meth:`~torrcast.usecases.torrent_claims.TorrentClaims.waited`): заводящий ждёт один
    снос, а не все. Остаток не теряется: оборванный проход - не «всё»,
    и следующее касание ряда сверяет снова (:class:`web.sweep_later.SweepLater`).
    """
    first = {_torrent_hash(entries[key].magnet) for key in continue_row(entries)[:WARM_ROW]}
    ours = {_torrent_hash(entry.magnet) for entry in entries.values()} - first - {""}
    refused: list[str] = []

    def free(torrent_hash: str) -> bool:
        if spared(torrent_hash):
            return False
        if engine.drop(torrent_hash):
            return True
        refused.append(torrent_hash)
        return False

    gone: list[str] = []
    for torrent_hash in sorted(ours & engine.hashes()):
        if CLAIMS.dropping(torrent_hash, free):
            gone.append(torrent_hash)
        if refused or CLAIMS.waited():
            return gone, False
    return gone, True
