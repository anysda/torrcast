"""Прогрев СЛЕДУЮЩЕЙ серии впрок - тем же механизмом, каким греется текущая.

Собирает его показ с первого кадра, забирает цепочка прогрева
(:meth:`torrcast.usecases.warm.warmer.Warmer._chain`).
"""

from __future__ import annotations

from pathlib import Path

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.episode_passport import episode_passport
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.worker_settings import WORKER_DUR
from torrcast.ports.torrent_engine import TorrentEngine
from torrcast.usecases.playback._recoder import _recoder
from torrcast.usecases.playback._warmer import _warmer
from torrcast.usecases.playback.entry_layout import entry_layout
from torrcast.usecases.playback.pack_container import pack_container
from torrcast.usecases.playback.voice_source import voice_source
from torrcast.usecases.warm.warmer import Warmer


def _next_warmer(
    config: Config,
    torrserver: TorrentEngine,
    torrent_hash: str,
    entry: Entry,
    profile: Profile = CAUTIOUS,
) -> Warmer | None:
    """Прогрев СЛЕДУЮЩЕЙ серии - тем же механизмом, каким грелась текущая.

    Собирается в отдельной нити с первого кадра текущей серии
    (:class:`torrcast.usecases.playback.following._PreparedFollowing`) и ждёт, пока живому окну
    показа нужен запас, - тем же правилом, каким замирает прогрев. Сбой не запоминается: цепочка
    прогрева (:meth:`torrcast.usecases.warm.warmer.Warmer._chain`) спросит снова, и сборка
    пойдёт заново. Греть следующую серию цепочка начинает только когда текущая легла на диск
    или её живая упаковка дошла до конца файла.

    ⚠️ Побочный смысл этой сборки не меньше самого прогрева. Автопереход на следующую
    серию (:func:`_cmd_worker`) начинается с двух вопросов к раздаче: паспорт файла
    (:func:`_state.probe` - длительность для порога перехода) и карта опорных кадров
    (:func:`torrcast.adapters.stream_pack.film_keys.film_keys` - сетка и манифест). Посреди обрыва
    связи спросить их не у кого, и показ, у которого следующая серия ЛЕЖИТ на диске, всё равно
    уткнулся бы в мёртвую раздачу. Здесь оба вопроса задаются заранее и оба ложатся в кэш на диск.

    ``None`` - греть нечего: фильм, последняя серия раздачи или запись без списка серий.
    """
    following = entry.advance()
    if following.done or not following.label:
        return None
    source = torrserver.stream_url(torrent_hash, following.file_idx)
    file_size = next(
        (item.size for item in torrserver.files(torrent_hash) if item.index == following.file_idx),
        0,
    )
    voice = voice_source(torrserver, torrent_hash, following)
    # 🔴 Вход раскладки - та же запись, что увидит показ
    # (:func:`torrcast.usecases.episode_duration._duration`), собранная тем же правилом, а
    # не свой пересказ паспорта: разойдись они - прогретое ляжет под другим ключом
    # (:func:`torrcast.usecases.warm.warm_key`), и показ своего же прогретого не найдёт.
    passport = episode_passport(following, _state.probe(source, timeout=WORKER_DUR))
    video_mbit = max(0.0, passport.vbps)
    grid, whole = entry_layout(config, source, passport, profile, file_size)
    recoder = (
        None
        if whole is not None
        else _recoder(
            source,
            following.audio,
            grid,
            # 🔴 Каталог тут ИМЕНУЕТСЯ, а не готовится. :func:`_state.hls_dir` готовит его
            # под НОВЫЙ показ: выметает сегменты, плейлист и флажок картинки. Звался он
            # отсюда посреди ИДУЩЕГО показа, в тот же каталог, и уносил его доказательство
            # (TC-884, 29-08-2026: флажок жил долю секунды, CLI не успел его увидеть и
            # погасил показ на 350 с бюджета). Место для кусков заводит сам кодировщик
            # (:meth:`torrcast.adapters.recode.recoder.Recoder.start`), уборка не нужна вовсе.
            Path(config.hls_dir) / _state.RECODE_DIR,
            config,
            video_mbit=video_mbit,
            profile=profile,
            video_mbit_estimated=passport.vbps_estimated,
            voice=voice,
        )
    )
    title = " ".join(filter(None, (following.title, following.label)))
    return _warmer(
        config,
        source,
        following.audio,
        grid,
        0.0,
        title,
        whole=whole,
        recoder=recoder,
        profile=profile,
        video_mbit=video_mbit,
        container=pack_container(profile, whole),
        voice=voice,
    )
