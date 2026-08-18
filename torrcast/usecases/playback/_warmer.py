"""Фоновый прогрев фильма на диск: этой серии и, лениво, следующей.

Собирает его показ (:func:`_play`), а цепочку серий тянет сам прогрев.
"""

from __future__ import annotations

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.worker_settings import WORKER_DUR
from torrcast.ports.journal import journal
from torrcast.ports.recode.encoding import Encoding
from torrcast.ports.recode.spot_rival import SpotRival
from torrcast.ports.torrent_engine import TorrentEngine
from torrcast.usecases.playback._layout import _layout
from torrcast.usecases.playback._recoder import _recoder
from torrcast.usecases.playback.following import Following
from torrcast.usecases.playback.media_grid import MediaGrid
from torrcast.usecases.warm import Vault, Warmer, warm_key, warm_root


def _warmer(
    config: Config,
    source: str,
    audio: int,
    grid: MediaGrid,
    start: float,
    title: str,
    whole: Encoding | None = None,
    recoder: SpotRival | None = None,
    follow: Following | None = None,
    profile: Profile = CAUTIOUS,
) -> Warmer | None:
    """Фоновый прогрев всего фильма на диск или ``None``, если он выключен.

    🔴 **Прогрев кодирует кусок ровно тем же решением, что и живая упаковка.** Куски
    одного показа приходят приёмнику из двух мест — из окна упаковки и с диска
    (:meth:`torrcast.usecases.feed_pack.feed.Feed.segment`), — и для приёмника это одна лента.
    Разойдись решение о кодировании, и на стыке двух источников меняется SPS: другой профиль, другая
    энтропийная кодировка, другая глубина буфера кадров — то есть декодер обязан
    переинициализироваться посреди фильма. Поэтому решение здесь ОДНО на обоих:

    * кодек, который приёмник не декодирует, — сплошной перекод (``whole``), и у показа,
      и у прогрева;
    * тяжёлые куски — точечный перекод тем же :class:`_state.Encode`, которым их берёт живой
      кодировщик (``recoder``), и ровно на тех же слотах;
    * всё остальное — копия.

    ⚠️ Прежде тут стояло «есть хоть один тяжёлый кусок — греть весь фильм перекодом».
    Замер на лёгком материале («Тачки 3»: 5 тяжёлых кусков из 525): живая упаковка отдавала
    копию релиза, а прогрев клал на диск сплошной ``ultrafast``, и SPS этих двух не
    совпадали ни одним байтом. Стык был не редкостью, а нормой работы — прогрев обгоняет
    показ и отдаёт ему свои куски.
    """
    if not config.warm:
        return None
    encode = whole
    spots = () if whole is not None or recoder is None else tuple(recoder.targets)
    # Решение точечного перекода спрашивается у самого кодировщика, а не у ``getattr``:
    # слоты непусты только тогда, когда кодировщик есть (:class:`SpotRival`).
    spot_encode = recoder.encode if spots and recoder is not None else None
    # Пресет и битрейт называет то решение, которым кусок и будет взят; решения нет
    # вовсе - и в записи стоят пустая строка и ноль, как стояли.
    decided: Encoding | None = spot_encode or encode
    vault = Vault(
        root=warm_root(config.warm_dir),
        key=warm_key(source, audio, grid, encode, spots),
        budget=int(config.warm_budget_gb * 1e9),
        title=title,
    )
    journal().plan(
        pack="recode" if encode is not None else "copy",
        warm="recode" if encode is not None else "copy",
        spots=len(spots),
        preset=decided.preset if decided is not None else "",
        mbit=decided.mbit if decided is not None else 0.0,
    )
    return Warmer(
        source=source,
        audio=audio,
        grid=grid,
        vault=vault,
        encode=encode,
        spots=spots,
        spot_encode=spot_encode,
        began_at=grid.slot_at(start),
        # Потолок веса куска - свойство приёмника, и прогреву он нужен ровно затем, чтобы
        # «прогрето NN» называло то, что показ и правда возьмёт с диска
        # (:attr:`torrcast.usecases.warm.Warmer.warmed`,
        # :meth:`torrcast.usecases.feed_pack.feed.Feed._warm`).
        cap=profile.max_segment_bytes,
        rate=config.warm_rate,
        follow=follow,
        rival=recoder,
        log=lambda text: print(text, flush=True),
    )


def _next_warmer(
    config: Config,
    torrserver: TorrentEngine,
    torrent_hash: str,
    entry: Entry,
    profile: Profile = CAUTIOUS,
) -> Warmer | None:
    """Прогрев СЛЕДУЮЩЕЙ серии - тем же механизмом, каким грелась текущая.

    Зовётся лениво и ровно один раз: когда текущая серия уже лежит на диске целиком и
    больше не нуждается ни в одном байте раздачи (:meth:`torrcast.usecases.warm.Warmer._chain`).
    Раньше этого момента следующая серия не имеет права ни на полосу, ни на процессор.

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
    media = _state.probe(source, timeout=WORKER_DUR)
    video_mbit = max(0.0, media.video_bps / 1e6)
    # 🔴 Профиль тот же, что у показа: разойдись они - прогретое ляжет под другим ключом
    # (:func:`torrcast.usecases.warm.warm_key`), и показ своего же прогретого не найдёт.
    grid, whole = _layout(
        config,
        source,
        media.duration,
        media.video or "",
        video_mbit,
        depth=media.depth,
        profile=profile,
        frame=media.frame,
        hdr=media.hdr,
    )
    recoder = (
        None
        if whole is not None
        else _recoder(
            source,
            following.audio,
            grid,
            _state.hls_dir(config.hls_dir) / _state.RECODE_DIR,
            config,
            video_mbit=video_mbit,
            profile=profile,
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
    )
