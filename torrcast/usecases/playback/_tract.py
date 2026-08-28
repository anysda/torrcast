"""Медиатракт одного показа: кодировщик, прогрев, упаковка, раздача и приёмник.

Собирает его показ (:func:`_play`) одним вызовом - на сетке и решении о перекодировании,
которые к этой секунде уже посчитаны и обязаны быть у всех участников одни и те же.
"""

from __future__ import annotations

from pathlib import Path

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.codec_tag import codec_tag
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.segment_container import MPEGTS
from torrcast.ports.receiver import Receiver
from torrcast.ports.recode.encoding import Encoding
from torrcast.ports.recode.spot_recoder import SpotRecoder
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.playback._cuttable import _Cuttable
from torrcast.usecases.playback._recoder import _recoder
from torrcast.usecases.playback._warmer import _warmer
from torrcast.usecases.playback.following import Following
from torrcast.usecases.playback.media_grid import MediaGrid
from torrcast.usecases.playback.stream_server import StreamServer
from torrcast.usecases.warm.warmer import Warmer


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
) -> tuple[SpotRecoder | None, Warmer | None, Feed, StreamServer, Receiver]:
    """Собрать тракт показа: кодировщик, прогрев, упаковку, раздачу и приёмник."""
    # Профиль тяжести всего фильма известен со старта - он считается из уже снятой
    # карты опорных кадров и не стоит ни одного запроса к рою. Тяжёлые куски кодировщик
    # начнёт перекодировать сразу, пока играет остальное.
    recoder = (
        None
        if whole is not None
        else _recoder(
            source,
            audio,
            grid,
            out / _state.RECODE_DIR,
            config,
            video_mbit=video_mbit,
            profile=profile,
            video_mbit_estimated=video_mbit_estimated,
            voice=voice,
        )
    )
    # Прогрев поднимается ПОСЛЕ старта показа (ниже), а собирается здесь: ему нужны и
    # сетка, и решение о перекодировании - те же, что у живой упаковки.
    container = profile.segment_container if whole is None else MPEGTS
    warmer = _warmer(
        config,
        source,
        audio,
        grid,
        start,
        about,
        whole=whole,
        recoder=recoder,
        follow=follow,
        profile=profile,
        video_mbit=video_mbit,
        container=container,
        voice=voice,
    )
    feed = Feed(
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
        cap=profile.max_segment_bytes,
        log=lambda text: print(text, flush=True),
        recoder=recoder,
        encode=whole,
        vault=None if warmer is None else warmer.vault,
    )
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
    return recoder, warmer, feed, server, receiver
