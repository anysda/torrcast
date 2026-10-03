"""Подаёт TorrServer описание раздачи (.torrent), пока рой не прислал его сам.

Служба кладёт поданное описание в уже добавленную магнетом раздачу (``SetInfoBytes``),
и файлы видны без пиров. Любой отказ - тишина: раздача остаётся на магнете, как была.

Ограждения:

- описание чужой раздачи не подаётся: infohash байтов обязан совпасть с хэшем;
- подаётся только раздаче в памяти и без описания (``stat`` 0 или 1 в ``list``).
  Повторная подача пересобирает куски, а ``get`` поднял бы закрытую раздачу из базы;
- раздачу, которую этот процесс снял (``drop``/``park``), описатель не трогает: снятие
  и подача разведены замком описателя (:mod:`torrcast.adapters.torrserver.describer`).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final

from torrcast.adapters.prowlarr.torrent_links import LINKS
from torrcast.adapters.torrserver.info_hash import info_hash
from torrcast.adapters.torrserver.torrent_store import STORE
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from collections.abc import Callable

#: ``TorrentAdded`` и ``TorrentGettingInfo``: раздача в памяти, описания ещё нет.
BARE: Final = frozenset({0, 1})


def describe(
    key: str,
    *,
    fetch: Callable[[str], bytes | None],
    stat: Callable[[str], int | None],
    upload: Callable[[str, bytes], bool],
    dropped: Callable[[str], bool],
) -> str:
    """Подать описание раздаче ``key``; вернуть исход словом для журнала.

    Верные байты, добытые по ссылке, ложатся на диск при любом исходе, кроме отказа:
    рой мог успеть первым, а закладке после перезапуска они пригодятся всё равно.
    """
    began = time.monotonic()
    source = "disk"
    data = STORE.stored(key)
    if data is None:
        url = LINKS.link_for(key)
        data = fetch(url) if url else None
        source = "link"
    outcome = _deliver(key, data, stat, upload, dropped)
    if data is not None and source == "link" and outcome not in {"no-torrent", "hash-mismatch"}:
        STORE.store(key, data)
    seconds = round(time.monotonic() - began, 3)
    journal().mark("описание", hash=key, source=source, outcome=outcome, seconds=seconds)
    return outcome


def _deliver(
    key: str,
    data: bytes | None,
    stat: Callable[[str], int | None],
    upload: Callable[[str, bytes], bool],
    dropped: Callable[[str], bool],
) -> str:
    if data is None:
        return "no-torrent"
    if info_hash(data) != key:
        return "hash-mismatch"
    if dropped(key):
        return "dropped"
    state = stat(key)
    if state is None:
        return "gone"
    if state not in BARE:
        return "swarm-first"
    return "uploaded" if upload(key, data) else "upload-failed"


__all__ = ["BARE", "describe"]
