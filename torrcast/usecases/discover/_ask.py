"""Один круг по индексерам и строки о выпавшем и об опоздавшем источнике."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.raw_result import RawResult
from torrcast.ports.progress.progress import Progress
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient


def _ask(client: IndexerClient, query: str, progress: Progress) -> list[RawResult]:
    """Один запрос к индексерам; пусто - это не ошибка, а повод переспросить иначе.

    🔴 TC-510. Выпавший источник называется вслух ОДНОЙ строкой и ровно один раз за
    поиск (:attr:`~torrcast.adapters.prowlarr.prowlarr.Prowlarr.reported_silent`), но выпасть он
    может двумя способами, и оба тут названы: молчун не ответил нам, а забаненного мы и не
    спрашивали - Prowlarr не дал (TC-259). Молча источник не выпадает: без этой строки «ничего не
    нашлось» звучит приговором каталогу, хотя спрошена была его часть.

    🔴 TC-703. Выпасть можно двумя способами, а НЕ ДОЕХАТЬ до этой выдачи - тремя:
    третий это опоздавший (:meth:`Prowlarr.waiting`). Круг уходит, когда ответили
    опорные, и тот, кто в эту секунду ещё в пути, в выдачу не попал - но и не пропал:
    его строки могут доехать позже. Слова у него поэтому свои. Молчун выпал совсем, и
    про него честно «выдача может быть хуже»; опоздавший ещё едет, и человеку сказано
    ровно это - выдача пока без него. Замер владельца: раздач у сериала было 131, прибор
    показал 2 и отказал, а в следе того же прогона четверть каталога значилась в пути.

    Источник называется ОДИН раз за поиск и одними словами: попавший и в молчуны, и в
    опоздавшие (опорного круг ждёт весь бюджет, а поток его живёт дальше) назван
    молчуном - это про ту секунду, в которую человек читает строку, правда.
    """
    try:
        rows = client.search(query)
    except NotFoundError:
        rows = []
    reported = client.reported_silent
    gone = [
        (name, why_gone)
        for names, why_gone in (
            (client.silent, phrase("discover.indexer_silent")),
            (client.banned, phrase("discover.indexer_banned")),
        )
        for name in names
        if name not in reported
    ]
    reported.update(name for name, _ in gone)
    if len(gone) == 1:
        progress.note(phrase("discover.indexer_one_gone", name=gone[0][0], why=gone[0][1]))
    elif gone:
        listed = ", ".join(f"{name} {why_gone}" for name, why_gone in gone)
        progress.note(phrase("discover.indexer_many_gone", listed=listed))
    late = [name for name in client.waiting() if name not in reported]
    reported.update(late)
    if len(late) == 1:
        progress.note(phrase("discover.indexer_one_late", name=late[0]))
    elif late:
        progress.note(phrase("discover.indexer_many_late", listed=", ".join(late)))
    return rows
