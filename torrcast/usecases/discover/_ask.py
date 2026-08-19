"""Один круг по индексерам и строка о выпавшем из каталога источнике."""

from __future__ import annotations

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
    """
    try:
        rows = client.search(query)
    except NotFoundError:
        rows = []
    # Через getattr, а не полем: в тестах на месте клиента стоят подделки, которые
    # обещают только `search`, и требовать от них весь договор Prowlarr незачем.
    reported: set[str] = getattr(client, "reported_silent", set())
    gone = [
        (name, why_gone)
        for names, why_gone in (
            (getattr(client, "silent", ()), "не ответил"),
            (getattr(client, "banned", ()), "недоступен"),
        )
        for name in names
        if name not in reported
    ]
    reported.update(name for name, _ in gone)
    if len(gone) == 1:
        progress.note(f"индексер {gone[0][0]} {gone[0][1]} - выдача может быть хуже")
    elif gone:
        listed = ", ".join(f"{name} {why_gone}" for name, why_gone in gone)
        progress.note(f"индексеры выпали из каталога: {listed} - выдача может быть хуже")
    return rows
