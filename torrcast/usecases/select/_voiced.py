"""Раздача, поднятая ради ``--voice``: у неё есть хозяин, пока её не принял показ."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import torrcast.usecases.select._pick_state as _pick_state
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.pick_settings import META_BUDGET, PROBE_BUDGET
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.progress import progress as progress_bar
from torrcast.usecases.rank.pick_voice import pick_voice
from torrcast.usecases.torrents import _held_by_show, _release_torrents

if TYPE_CHECKING:
    from torrcast.domain.args import Args


@dataclass(slots=True)
class _Voiced:
    """Раздача, поднятая ради ``--voice``: у неё есть хозяин, пока её не принял показ.

    Дорожки читаются из потока, а поток начинается с раздачи в TorrServer — и раздача
    эта переживает наш процесс: живёт она в чужой памяти до перезапуска службы. Пока
    хозяина у неё не было, каждый вызов с ``--voice`` оставлял по раздаче навсегда, в том
    числе ``--dry``, который заведён ровно затем, чтобы следов не оставлять.

    Хозяин один и меняется один раз: если показ поднялся на том же магните, раздача
    достаётся юниту (:attr:`handed`), и убирает её он (:func:`_cmd_worker`). Во всех
    остальных исходах её убирает :meth:`drop` — по СВОЕМУ хэшу, чужого не касаясь.
    """

    torrent_hash: str = ""
    #: Показ принял эту раздачу: юнит играет тот же магнит и уберёт её за собой сам.
    handed: bool = False

    def drop(self, config: Config, release: Callable[..., None] | None = None) -> None:
        """Убрать, если так и не пригодилась. Повторный вызов и пустой хэш безвредны.

        Кроме одного случая: ту же раздачу держит живой показ - ``cast --voice`` на
        играющий фильм поднимает её же (``add`` идемпотентен), и снос выдернул бы её
        из-под экрана (:func:`_held_by_show`). Уберёт её хозяин показа сам.

        ``release`` - чем сносить: подделке отбора хватает списка хэшей, в бою это
        поход в TorrServer.
        """
        if self.handed or not self.torrent_hash:
            return
        torrent_hash, self.torrent_hash = self.torrent_hash, ""
        if _held_by_show(torrent_hash):
            return
        with contextlib.suppress(TorrcastError):
            (release or _release_torrents)(config, [torrent_hash])


def _voiced(config: Config, entry: Entry, args: Args, own: _Voiced | None = None) -> Entry:
    """Запись с учётом ``--voice``; без флага — она же, не тронутая и без похода в рой.

    Флага нет — не читаем ничего: этот путь тем и хорош, что обходится состоянием.
    ⚠️ Звать только тогда, когда запись действительно пойдёт в показ. Живая грабля:
    вызов до проверки «есть ли что продолжать» лез в TorrServer за раздачей,
    которую никто играть не собирался, и падал на её магните.

    ``own`` — хозяин поднятой раздачи (:class:`_Voiced`): в списке службы лежат и чужие,
    своей её там ничто не называет, и убрать её можно только по хэшу, который знает он.
    Хозяина не назвали — раздача убирается тут же, на выходе: бесхозной она не остаётся
    ни в одном случае.
    """
    if args.voice is None:
        return entry
    if own is not None:
        return _revoice(config, entry, args, own)
    orphan = _Voiced()
    try:
        return _revoice(config, entry, args, orphan)
    finally:
        orphan.drop(config)


def _revoice(config: Config, entry: Entry, args: Args, own: _Voiced) -> Entry:
    """``--voice`` поверх сохранённого выбора: перечитать дорожки раздачи и взять нужную.

    Нужно ровно для сериала и продолжения: там показ идёт по записи состояния и потока
    никто не читает — ни номеров дорожек, ни подписей взять неоткуда. Платим за это
    метаданными раздачи и одним ffprobe (секунды, с живым прогрессом), и платим только
    когда флаг назван: счастливый путь этой цены не видит.

    Состояние отсюда не пишется: выбор уезжает в запись показа (:func:`_launch`) вместе
    с позицией и серией. Так у ``--dry`` не остаётся следов, а память не переписывается
    показом, который не начался.

    ⚠️ Следов не остаётся и в TorrServer: поднятая здесь раздача записывается хозяину
    (``own``) сразу же, той же строкой, что и поднимается. Раньше её не убирал никто -
    ни при сухом прогоне, ни когда показ до старта так и не доходил.
    """
    torrserver = _pick_state._select_engines(config.torrserver_url)
    with progress_bar() as progress:
        progress.phase("дорожки")
        own.torrent_hash = torrent_hash = torrserver.add(entry.magnet)
        torrserver.wait_files(torrent_hash, timeout=META_BUDGET)
        media = _pick_state._select_prober(
            torrserver.stream_url(torrent_hash, entry.file_idx), timeout=PROBE_BUDGET
        )
        progress.phase("")
    entry.audio, entry.voice = pick_voice(media, args, entry.voice)
    return entry
