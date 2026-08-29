"""Цикл показа внутри юнита: серия за серией, пока сериал не кончится.
Крутит его :func:`torrcast.usecases.worker._cmd_worker`.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from torrcast.domain.config import Config
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import Profile
from torrcast.domain.voice_swap import voice_swap
from torrcast.domain.worker_settings import WORKER_META
from torrcast.ports.journal.slot import journal
from torrcast.ports.receiver import Receiver
from torrcast.ports.state_store.slot import store
from torrcast.ports.stream_source import StreamSource
from torrcast.ports.torrent_engine import TorrentEngine
from torrcast.usecases.episode_duration import _duration
from torrcast.usecases.following import _following
from torrcast.usecases.next_season import _next_season
from torrcast.usecases.playback._next_warmer import _next_warmer
from torrcast.usecases.playback._play import _play
from torrcast.usecases.playback.voice_source import voice_source
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
    next_season: Callable[..., bool] = _next_season,
) -> int:
    """Сам цикл показа: серия за серией, пока сериал не кончится. Раздачи, которые он
    поднял, складываются в ``mine`` — их убирает :func:`_cmd_worker` на выходе.

    Конец раздачи сезона - не конец цикла: досмотренному сезону цикл сперва ищет
    следующий (:func:`torrcast.usecases.next_season._next_season`) и играет его с первой серии.

    Сам показ серии и поиск следующего сезона названы аргументами с боевым умолчанием:
    работа этой единицы - очередь серий, учёт раздачи и то, с какими числами показ зовут,
    а не HLS, ffmpeg, приёмник и поиск за ними.
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
        voice = voice_source(torrserver, torrent_hash, entry)
        entry = _duration(key, entry, source)
        supply.file_index, supply.duration = entry.file_idx, entry.dur
        watch = Watch(key=key, entry=entry)
        title = " ".join(filter(None, (entry.title, entry.label)))
        # 🔴 Подпись показа - единственное, что уезжает на ЭКРАН, и подмена озвучки
        # обязана доехать именно туда: запомненной студии в этом релизе не нашлось,
        # играет другая, а зритель сидит перед телевизором, а не перед терминалом
        # (:func:`voice_swap`). В след и в консоль идёт та же подпись без приписки:
        # там подмена уже названа своим полем записи.
        shown = " · ".join(filter(None, (title, voice_swap(entry.studio, entry.heard))))
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
            shown,
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
            # диске (:meth:`torrcast.usecases.warm.warmer.Warmer._chain`). Раздача та же, файл -
            # соседний.
            follow=partial(_next_warmer, config, torrserver, torrent_hash, entry, profile),
            supply=supply,
            profile=profile,
            session_tag=session_tag,
            # Звук отдельным файлом рядом с видео: второй вход упаковки, если он есть.
            voice=voice,
        )
        if watch.closed_by_remote:
            # TC-880: закладка уже сдвинута на следующую серию (:meth:`Watch.close`), но
            # поднимать показ на приёмнике после воли зрителя нельзя - сеанс кончается
            # на месте, следующая серия ждёт следующего `cast`.
            return code
        following = _following(key) if watch.done else None
        # Конец раздачи сезона - не конец сериала (TC-805): следующий сезон ищется
        # и записывается в состояние здесь, и цикл играет его, как играл бы следующую
        # серию внутри пака. Не нашёлся - строка уже сказана, и показ заканчивается.
        if following is None and watch.done and next_season(config, key, torrserver, profile):
            following = _following(key)
        if following is None:
            return code
        print(f"следующая серия: {following.label}", flush=True)
