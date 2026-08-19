"""Цикл показа внутри юнита: серия за серией, пока сериал не кончится.
Крутит его :func:`torrcast.usecases.worker._cmd_worker`.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from torrcast.domain.config import Config
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import Profile
from torrcast.domain.worker_settings import WORKER_META
from torrcast.ports.journal import journal
from torrcast.ports.receiver import Receiver
from torrcast.ports.state_store import store
from torrcast.ports.stream_source import StreamSource
from torrcast.ports.torrent_engine import TorrentEngine
from torrcast.usecases.episode_duration import _duration
from torrcast.usecases.following import _following
from torrcast.usecases.playback import _next_warmer, _play
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.start_clock import _Clock
from torrcast.usecases.torrents import _own_torrent
from torrcast.usecases.watch import Watch

#: Чем снимается снимок порогов серии: какими числами играем и откуда взято каждое.
#: Собрать его может только тот, кто видит и настройки, и приёмник, поэтому кладёт сюда
#: композиционный корень (:mod:`torrcast.runtime.wire`).
_worker_thresholds: Callable[[Config, Profile], dict[str, object]]


def _configure_worker_loop(thresholds: Callable[[Config, Profile], dict[str, object]]) -> None:
    """Назначить, чем цикл снимает пороги начала серии."""
    global _worker_thresholds
    _worker_thresholds = thresholds


def _worker_loop(
    config: Config,
    key: str,
    torrserver: TorrentEngine,
    receiver: Receiver,
    supply: StreamSource,
    mine: list[str],
    profile: Profile,
    *,
    play: Callable[..., int] = _play,
) -> int:
    """Сам цикл показа: серия за серией, пока сериал не кончится. Раздачи, которые он
    поднял, складываются в ``mine`` — их убирает :func:`_cmd_worker` на выходе.

    Сам показ серии назван аргументом с боевым умолчанием: работа этой единицы -
    очередь серий, учёт раздачи и то, с какими числами показ зовут, а не HLS, ffmpeg и
    приёмник за ним.
    """
    magnet, torrent_hash = "", ""
    while True:
        entry = store().load().get(key)
        if entry is None:
            raise InfraError(f"в состоянии нет записи {key}")
        if entry.magnet != magnet:  # раздача та же - метаданные второй раз не ждём
            magnet = entry.magnet
            torrent_hash = torrserver.add(magnet)
            mine.append(torrent_hash)  # с этой секунды у раздачи есть хозяин - этот юнит
            # ...и с этой же секунды имя хозяина знает состояние: умри мы по SIGKILL,
            # хэш - единственное, чем раздачу потом убрать (:func:`_release_orphans`).
            # Поле правится и в своей копии записи: её кладёт на диск сторож позиции.
            entry.torrent = torrent_hash
            _own_torrent(key, torrent_hash)
            torrserver.wait_files(torrent_hash, timeout=WORKER_META)
            # Тот же магнит, но живёт он теперь и у сторожа: URL потока несёт только хэш,
            # и вернуть раздачу с трекерами после аварии источника может лишь он
            # (:class:`torrcast.ports.stream_source.StreamSource`). За магнитом в индексеры
            # мы не ходим - он лежит в записи картины.
            supply.torrent_hash, supply.magnet, supply.lost = torrent_hash, magnet, ""
        source = torrserver.stream_url(torrent_hash, entry.file_idx)
        entry = _duration(key, entry, source)
        watch = Watch(key=key, entry=entry)
        title = " ".join(filter(None, (entry.title, entry.label)))
        sid = journal().start_session()
        session_tag = f"[сеанс {sid}]"
        # Профиль идёт в след каждой серией: по какому набору порогов играли - вопрос,
        # который иначе снова пришлось бы выяснять с гипервизора.
        journal().emit(
            "session",
            "session_start",
            title=title,
            pos=round(entry.pos, 1),
            profile=profile.key,
            **_worker_thresholds(config, profile),
        )
        print(f"{session_tag} показ «{title}» с {_hms(entry.pos)}", flush=True)
        code = play(
            config,
            source,
            entry.audio,
            title,
            _Clock(),
            watch,
            receiver=receiver,
            codec=entry.codec,
            # Кодек без глубины цвета - половина паспорта: Hi10P зовётся тем же h264.
            depth=entry.depth,
            # И кадр туда же: 2160p приёмник не берёт ни в каком кодеке, его ужимает
            # перекод (TC-221/TC-222). HDR - чем красить ужатое (TC-223).
            frame=entry.frame,
            hdr=entry.hdr,
            # Прогрев следующей серии впрок: собирается лениво, когда текущая уже на
            # диске (:meth:`torrcast.usecases.warm.Warmer._chain`). Раздача та же, файл - соседний.
            follow=partial(_next_warmer, config, torrserver, torrent_hash, entry, profile),
            supply=supply,
            profile=profile,
            session_tag=session_tag,
        )
        following = _following(key) if watch.done else None
        if following is None:
            return code
        print(f"следующая серия: {following.label}", flush=True)
