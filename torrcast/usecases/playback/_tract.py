"""Медиатракт одного показа: кодировщик, прогрев, упаковка, раздача и приёмник.

Собирает его показ (:func:`_play`) одним вызовом - на сетке и решении о перекодировании,
которые к этой секунде уже посчитаны и обязаны быть у всех участников одни и те же.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.codec_tag import codec_tag
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.ports.receiver import Receiver
from torrcast.ports.recode.encoding import Encoding
from torrcast.ports.recode.spot_recoder import SpotRecoder
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.feed_pack.feed_segment import _stocked
from torrcast.usecases.playback._cuttable import _Cuttable
from torrcast.usecases.playback._end_ahead import _Ahead
from torrcast.usecases.playback._ending import _Ending
from torrcast.usecases.playback._show_parts import _show_parts
from torrcast.usecases.playback.ended_feed import EndedFeed
from torrcast.usecases.playback.entry_layout import entry_layout
from torrcast.usecases.playback.following import Following
from torrcast.usecases.playback.media_grid import MediaGrid
from torrcast.usecases.playback.pack_container import pack_container
from torrcast.usecases.playback.stream_server import StreamServer
from torrcast.usecases.warm.warmer import Warmer
from torrcast.usecases.watch import Watch


def _tract(
    config: Config,
    source: str,
    audio: int,
    about: str,
    out: Path,
    grid: MediaGrid,
    whole: Encoding | None,
    start: float,
    video_mbit: float,
    tls: bool,
    receiver: Receiver | None,
    follow: Following | None = None,
    profile: Profile = CAUTIOUS,
    video_mbit_estimated: bool = False,
    codec: str = "",
    depth: int = 0,
    voice: str = "",
    *,
    watch: Watch | None = None,
    supply: StreamSource | None = None,
    ahead: _Ahead | None = None,
    file_size: int = 0,
) -> tuple[SpotRecoder | None, Warmer | None, EndedFeed, StreamServer, Receiver]:
    """Собрать тракт показа: кодировщик, прогрев, упаковку, раздачу и приёмник.

    ``ahead`` - паспорт, который показ дочитывает сам, когда на экране первый кадр
    (:func:`torrcast.usecases.playback._end_ahead._end_ahead`): старт его не ждёт, а конец
    картинки, разошедшийся с записью, пересобирает сетку впереди упаковки (:class:`_Ending`).
    """
    # Профиль тяжести всего фильма известен со старта - он считается из уже снятой
    # карты опорных кадров и не стоит ни одного запроса к рою. Тяжёлые куски кодировщик
    # начнёт перекодировать сразу, пока играет остальное. Прогрев поднимается ПОСЛЕ старта
    # показа, а собирается здесь: ему нужны и сетка, и решение о перекодировании - те же,
    # что у живой упаковки. Сборка одна и для пересборки по концу картинки (``parts``).
    container = pack_container(profile, whole)
    parts = partial(
        _show_parts,
        config,
        source,
        audio,
        about,
        out,
        whole=whole,
        start=start,
        video_mbit=video_mbit,
        follow=follow,
        profile=profile,
        video_mbit_estimated=video_mbit_estimated,
        container=container,
        voice=voice,
    )
    recoder, warmer = parts(grid=grid)
    feed = EndedFeed(
        source=source,
        audio=audio,
        voice=voice,
        out=out,
        grid=grid,
        container=container,
        video_codec=codec_tag(codec, depth),
        readrate=config.hls_readrate,
        burst=config.hls_burst,
        keep=config.hls_keep,
        # Сколько держать запрос вместо 404 - свойство приёмника: Q70D после 404 молчит
        # минутами, а приставка Android TV берёт следующий LOAD через девять секунд.
        wait=profile.hold_seconds,
        # Потолок веса куска нужен раздаче отдельно от сетки: прогретое на диске уезжает
        # на ТВ мимо упаковки, и взвесить его больше негде (:meth:`Feed._warm`).
        cap=profile.segment_limit,
        # Порог «ждать или перепаковать» и задел подъёма на стыке прогретого - тоже
        # свойства приёмника, и приходят они настройкой, а не умолчанием класса: руками
        # написанное сильнее профиля (:func:`torrcast.domain.tune.tune`).
        jump=config.hls_jump,
        seam_lead=config.hls_seam_lead,
        log=lambda text: print(text, flush=True),
        recoder=recoder,
        encode=whole,
        vault=None if warmer is None else warmer.vault,
    )
    if recoder is not None:
        # Прогретый перекод показ берёт с диска, и кодировать его второй раз - отнимать ядра
        # у соседних тяжёлых мест (у следующей серии на стыке - у её первых секунд).
        recoder.stock(partial(_stocked, feed))
    server = _state.HlsServer(
        out,
        config.hls_cert,
        config.hls_key,
        port=config.hls_port,
        tls=tls,
        feed=feed,
        warm_recodes=set() if warmer is None else warmer.vault.served,
    )
    # Серт приёмнику нужен только затем, чтобы проверить нашу раздачу: по http проверять
    # нечего, и mock не должен делать вид, что что-то проверил. Готовый приёмник приходит
    # с сериалом: он один на весь юнит (см. :func:`_cmd_worker`).
    if receiver is None:
        receiver = _state.make_receiver(
            config.receiver, config.tv or "", config.hls_cert if tls else "", profile=profile
        )
    if hasattr(receiver, "segment_container"):
        receiver.segment_container = container
    # Сетку знает показ, а спотыкается о неё приёмник: и прыжок сторожа, и подъём после
    # отказа обязаны мерить кусками, а не секундами
    # (:meth:`torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver._nudge`).
    # Приёмник живёт весь юнит и достаётся следующей серии - сетка у неё своя, и назвать её надо
    # каждой.
    if isinstance(receiver, _Cuttable):
        receiver.next_cut = grid.after
    if ahead is not None and watch is not None:
        relayout = partial(entry_layout, config, source, watch.entry, profile, file_size)
        ending = _Ending(
            ahead,
            watch,
            supply,
            relayout,
            parts,
            feed,
            server,
            receiver,
            recoder,
            warmer,
            start,
            picture=_state.playing_flag(out).exists,
            go=ahead.go,
        )
        feed.settle, feed.tick = ending, ending.tick
    return recoder, warmer, feed, server, receiver
