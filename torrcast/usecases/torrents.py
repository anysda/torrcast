"""Уборка своих раздач в TorrServer: чей хэш, кто его держит и когда его сносить.
Зовут отсюда показ, отбор и ``cast stop``; сеть и диск приходят готовыми зависимостями.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence

from torrcast.domain.config import Config
from torrcast.domain.probe_settings import PROBE_TIMEOUT
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.show_unit import unit
from torrcast.ports.state_store import store
from torrcast.ports.torrent_engines import TorrentEngines

#: Чем сценарий берёт службу раздач: адрес и срок ответа знает он, саму службу - корень
#: (:mod:`torrcast.runtime.wire`).
_cleanup_engines: TorrentEngines


def _configure_torrents(engines: TorrentEngines) -> None:
    """Назначить, чем сценарий берёт службу раздач."""
    global _cleanup_engines
    _cleanup_engines = engines


def _release_torrents(config: Config, hashes: Sequence[str]) -> list[str]:
    """Убрать свои раздачи по ЯВНЫМ хэшам; возвращает те, которых в службе больше нет.

    🔴 Именно по хэшам, а не «всё, что видно в списке службы»: в списке лежат и ЧУЖИЕ
    раздачи, и «снести всё из list» уже сносило их. Здесь список не спрашивается ни разу.

    ⚠️ Обоснование у правила именно это, а не «своих в списке всё равно не видно»:
    проверено на TorrServer MatriX.142.2 - наша раздача видна в ``action:list`` весь
    показ. Пропадает она из списка только ПОСЛЕ перезапуска службы (``save_to_db:false``),
    и это отдельный довод за явный хэш, а не за чистку списком.

    Срок службе даётся короткий (:data:`torrcast.domain.probe_settings.PROBE_TIMEOUT`), а молчание не
    считается бедой: уборка идёт на выходе, в том числе по SIGTERM от ``cast stop``, и
    задерживать выход из-за неотвечающей службы она права не имеет. Повторный снос
    несуществующей раздачи - не ошибка (:meth:`torrcast.ports.torrent_engine.TorrentEngine.drop`).

    🔴 Но молчание - и не уборка, а разница между ними видна только отсюда. Зовущие по
    этому ответу решают, забывать ли хэш: забытый хэш нечем снести, а раздача переживает
    свой процесс и живёт в службе до её перезапуска.
    """
    gone: list[str] = []
    if not hashes:
        return gone
    torrserver = _cleanup_engines(config.torrserver_url, timeout=PROBE_TIMEOUT)
    for torrent_hash in dict.fromkeys(h for h in hashes if h):
        with contextlib.suppress(TorrcastError):
            if torrserver.drop(torrent_hash):
                gone.append(torrent_hash)
    return gone


def _own_torrent(key: str, torrent_hash: str) -> None:
    """Отметить в состоянии хэш раздачи, которую держит показ; пусто - снять отметку.

    Записывается в тот же момент, когда юнит раздачу поднял, и снимается тогда, когда он
    её убрал: между этими двумя секундами запись и есть единственный след того, кому
    раздача принадлежит (:attr:`torrcast.state.Entry.torrent`).

    Состояние перечитывается: рядом мог писать сторож позиции.
    """
    state = store().load()
    entry = state.get(key)
    if entry is None or entry.torrent == torrent_hash:
        return
    entry.torrent = torrent_hash
    state.put(key, entry)
    store().save(state)


def _release_orphans(config: Config) -> None:
    """Убрать раздачу, чей хозяин умер не по-людски: SIGKILL по таймауту, паника, ребут.

    Юнит убирает своё сам на любом штатном выходе, но SIGKILL не спрашивает, и хэш умирал
    вместе с процессом: раздача оставалась в TorrServer навсегда - до его перезапуска, - а
    убрать её было нечем («снести всё из list» снесло бы чужое). Теперь хэш лежит
    в состоянии, и сирота живёт максимум до следующего запуска.

    🔴 Мёртвым хозяин считается по ЖИВОСТИ юнита, а не по наличию записи: идёт показ -
    раздача его, и трогать её нельзя. Убирается только то, что записано явным хэшем,
    повторный снос уже убранной - не ошибка
    (:meth:`torrcast.ports.torrent_engine.TorrentEngine.drop`).

    🔴 Забывается хэш только вместе с раздачей. Служба, которая не ответила, ничего не
    убрала, а запись - единственное, чем эту раздачу вообще можно снести: стерев её за
    молчание, мы делали сироту вечной. Не убралось - не забываем, попробуем в другой раз.
    """
    state = store().load()
    orphans = {key: entry.torrent for key, entry in state if entry.torrent}
    if not orphans:  # обычный случай, и он не стоит ни одного вопроса systemd
        return
    if unit().active():  # показ идёт - раздача под ним живая, и она не сирота
        return
    gone = set(_release_torrents(config, list(orphans.values())))
    if not gone:  # службы нет - сироты остались сиротами, и запись о них тоже
        return
    for key, torrent_hash in orphans.items():
        if torrent_hash in gone:  # не через put: уборка мусора не делает запись «свежей»
            state.entries[key].torrent = ""
    store().save(state)


def _held_by_show(torrent_hash: str) -> bool:
    """Правда ли, что раздачу держит показ: её хэш записан в состоянии хозяином.

    Параллельный ``cast`` греет раздачи той же выдачи, что стоит на экране (досмотр
    сериала из той же раздачи, ``cast voices`` на играющий фильм), а ``add`` в TorrServer
    идемпотентен - и раздача живого показа оказывается среди прогретых. Снести её на
    уборке прогрева - выдернуть источник из-под экрана, поэтому каждый такой снос
    спрашивает состояние.

    Счётчика владения тут не нужно: двух держателей не бывает по устройству
    (:meth:`torrcast.domain.watch_state.WatchState.held`). А systemd нарочно не спрашивается:
    так нет ни окна гонки на старте юнита (``is-active`` отвечает «active» не в первую же
    секунду), ни цены на счастливом пути - одно чтение файла на снос, а сносы не горячий
    путь.

    Цена консервативности: хэш, забытый убитым юнитом (SIGKILL), прогрев сносить не
    станет - за него уберёт :func:`_release_orphans` при следующем запуске показа.
    """
    return bool(torrent_hash) and torrent_hash in store().load().held()
