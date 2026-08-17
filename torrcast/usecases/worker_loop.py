"""Цикл показа внутри юнита: серия за серией, пока сериал не кончится.
Крутит его :func:`torrcast.usecases.worker._cmd_worker`.
"""

# ruff: noqa: F821, F822

from __future__ import annotations

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import Profile
from torrcast.domain.worker_settings import WORKER_META
from torrcast.ports.journal import journal

__all__ = [
    "WORKER_META",
    "Config",
    "Entry",
    "InfraError",
    "Profile",
    "Receiver",
    "State",
    "Supply",
    "TorrServer",
    "Watch",
    "_Clock",
    "_duration",
    "_following",
    "_own_torrent",
    "_worker_loop",
    "partial",
    "trace_thresholds",
]

from functools import partial

from torrcast.ports.module import module
from torrcast.usecases.episode_duration import _duration
from torrcast.usecases.following import _following
from torrcast.usecases.playback import _next_warmer, _play
from torrcast.usecases.rank import _hms
from torrcast.usecases.start_clock import _Clock
from torrcast.usecases.torrents import _own_torrent
from torrcast.usecases.watch import Watch

for _module_name, _names in {
    "torrcast.cast": ("Receiver",),
    "torrcast.state": ("State",),
    "torrcast.stream": (
        "Supply",
        "TorrServer",
    ),
    "torrcast.profile": ("trace_thresholds",),
}.items():
    _dependency = module(_module_name)
    globals().update({name: getattr(_dependency, name) for name in _names})


def _worker_loop(
    config: Config,
    key: str,
    torrserver: TorrServer,
    receiver: Receiver,
    supply: Supply,
    mine: list[str],
    profile: Profile,
) -> int:
    """Сам цикл показа: серия за серией, пока сериал не кончится. Раздачи, которые он
    поднял, складываются в ``mine`` — их убирает :func:`_cmd_worker` на выходе.
    """
    magnet, torrent_hash = "", ""
    while True:
        entry = State.load().get(key)
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
            # (:class:`torrcast.stream.Supply`). За магнитом в индексеры мы не ходим - он
            # лежит в записи картины.
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
            **trace_thresholds(config, profile),
        )
        print(f"{session_tag} показ «{title}» с {_hms(entry.pos)}", flush=True)
        code = _play(
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
            # диске (:meth:`torrcast.warm.Warmer._chain`). Раздача та же, файл - соседний.
            follow=partial(_next_warmer, config, torrserver, torrent_hash, entry, profile),
            supply=supply,
            profile=profile,
            session_tag=session_tag,
        )
        following = _following(key) if watch.done else None
        if following is None:
            return code
        print(f"следующая серия: {following.label}", flush=True)
