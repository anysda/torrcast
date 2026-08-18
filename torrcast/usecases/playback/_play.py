"""Показ целиком: упаковка → раздача по http на голом IP → приёмник.

Зовёт его юнит показа (:func:`torrcast.usecases.worker._cmd_worker`), и только он.
"""

from __future__ import annotations

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.domain.why import why
from torrcast.ports.journal import journal
from torrcast.ports.receiver import Receiver
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.playback._layout import _layout
from torrcast.usecases.playback._show_end import _close_show, _report_end, _say_whole
from torrcast.usecases.playback._tract import _tract
from torrcast.usecases.playback.following import Following
from torrcast.usecases.revive_playback import _hold
from torrcast.usecases.start_clock import _Clock
from torrcast.usecases.watch import Watch


def _play(
    config: Config,
    source: str,
    audio: int,
    about: str,
    clock: _Clock,
    watch: Watch | None = None,
    duration: float = 0.0,
    receiver: Receiver | None = None,
    codec: str = "",
    depth: int = 0,
    follow: Following | None = None,
    supply: StreamSource | None = None,
    profile: Profile = CAUTIOUS,
    frame: int = 0,
    hdr: bool = False,
    session_tag: str = "",
) -> int:
    """Упаковка → раздача по http на голом IP → приёмник. Своих демонов нет: и ffmpeg,
    и раздача живут ровно на время показа и гасятся вместе с ним, что бы ни случилось.

    Упаковка за показ перезапускается столько раз, сколько человек перемотал: манифест
    обещает приёмнику весь фильм, а :class:`Feed` пакует то место, которое он попросил.
    Раздача, приёмник и LOAD при этом одни на весь показ.

    ``follow`` - чем прогреву заняться, когда эта серия ляжет на диск целиком
    (:attr:`torrcast.usecases.warm.Warmer.follow`); у фильма его нет и быть не может.

    ``supply`` - источник показа (:class:`torrcast.ports.stream_source.StreamSource`): служба и наша
    раздача в ней. Спрашивают его только на краю показа, зато прежде, чем объявить показ
    погасшим, - иначе за аварию источника отвечает приёмник, который ни при чём.

    ``profile`` - пороги ПРИЁМНИКА (:mod:`torrcast.domain.profile`): вес куска, терпение, сторож
    нуджей, удержание запроса вместо 404. Умолчание осторожное - тот же Q70D, что и был.
    """
    out = _state.hls_dir(config.hls_dir)
    start = watch.entry.pos if watch else 0.0
    length = watch.entry.dur if watch else duration
    tls = config.transport == "https"
    video_mbit = max(0.0, watch.entry.vbps) if watch else 0.0
    session_tag = session_tag or f"[сеанс {journal().session_id()}]"
    # Сетка сегментов снимается с самого файла и дальше не меняется: она же в манифесте,
    # она же в команде ffmpeg. Всё, что показ говорит о времени, считается по ней.
    #
    # Сетке нужен не только шаг, но и вес. Сегмент тяжелее ~19 МБ приёмник не
    # доигрывает, а выбрасывает буфер и качает его заново, поэтому граница ставится с
    # оглядкой на предсказанный вес куска - а он зависит и от паспорта (что уедет на ТВ),
    # и от того, перекодируем ли мы тяжёлое (тогда кусок не тяжелее ``recode_mbit``).
    # Кодек, который приёмник не декодирует, - это решение на весь показ, а не на кусок:
    # перекодирует сама упаковка, одним прогоном, и кодировщик тяжёлых кусков не нужен -
    # перекодировать поверх перекода нечего. Решается это ДО сетки: от битрейта перекода
    # зависит вес каждого куска, а значит и то, где сетка поставит границы.
    grid, whole = _layout(
        config,
        source,
        length,
        codec,
        video_mbit,
        say=lambda text: print(text, flush=True),
        depth=depth,
        profile=profile,
        frame=frame,
        hdr=hdr,
    )
    journal().mark("сетка", сегментов=grid.count, покадрам=grid.on_keys)
    if whole is not None:
        _say_whole(whole, codec, depth, video_mbit, frame, profile)
    recoder, warmer, feed, server, receiver = _tract(
        config,
        source,
        audio,
        about,
        out,
        grid,
        whole,
        start,
        video_mbit,
        tls,
        receiver,
        follow=follow,
        profile=profile,
    )
    url = f"{_state.hls_base(config)}/index.m3u8"
    try:
        server.start()
        journal().mark("раздача")
        # Упаковку начинаем сами, не дожидаясь первого запроса: ресиверу нужен готовый
        # кусок сразу, иначе LOAD упирается в ожидание ffmpeg и старт растёт на глазах.
        if recoder is not None:
            recoder.played = start
            recoder.start()
        feed.restart(grid.slot_at(start))
        journal().mark("упаковка пошла")
        raised = True
        try:
            receiver.play(url, about, at=start)
        except StartRefusedError as exc:
            # 🔴 Отказ на первом LOAD показ больше не хоронит. Приёмник в сети, фильм на
            # месте, упаковка идёт - и единственное, чего не хватает, это ещё одного
            # захода в чистое приложение. Ровно это умеет лестница воскрешения, и она же
            # чинит такой отвал посреди фильма (:meth:`_Revival.resurrect`): показ,
            # которого не было, поднимается тем же путём, что и погасший.
            # ⚠️ Ловится именно отказ ЗАГРУЗКИ, а не любая авария: приёмника нет в сети -
            # это другая беда и другой класс
            # (:class:`torrcast.domain.start_refused_error.StartRefusedError`), и висеть с ней
            # перед пустым экраном весь бюджет старта незачем.
            raised = False
            print(f"{session_tag} {why(exc)} - поднимаю показ сам", flush=True)
        else:
            journal().mark("LOAD взят")
            print(f"{session_tag} играю {about} - на ТВ   (старт {clock.total:.0f} с)", flush=True)
        # ⚠️ Прогрев стартует ровно ЗДЕСЬ и ни строкой выше: путь до картинки он не
        # удлиняет ни на секунду - ни своим ffmpeg, ни чтением каталога. Всё, что он
        # делает, происходит уже при играющем показе и на остатке процессора.
        if warmer is not None:
            warmer.start()
        expected_end = _hold(
            receiver,
            feed,
            watch,
            warmer,
            supply,
            profile,
            session_tag=session_tag,
            start=start,
            raised=raised,
        )
    finally:
        _close_show(watch, warmer, receiver, feed, server)

    return _report_end(receiver, session_tag, watch, supply, expected_end)
