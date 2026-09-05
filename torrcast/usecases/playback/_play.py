"""Показ целиком: упаковка → раздача по http на голом IP → приёмник.

Зовёт его юнит показа (:func:`torrcast.usecases.worker._cmd_worker`), и только он.
"""

from __future__ import annotations

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.domain.why import why
from torrcast.ports.journal.slot import journal
from torrcast.ports.receiver import Receiver
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.playback._show_end import _close_show, _report_end, _say_whole
from torrcast.usecases.playback._tract import _tract
from torrcast.usecases.playback.following import Following
from torrcast.usecases.playback.hls_root import hls_root
from torrcast.usecases.playback.layout import layout
from torrcast.usecases.revive_playback._hold import _hold
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
    voice: str = "",
) -> int:
    """Упаковка → раздача по http на голом IP → приёмник. Своих демонов нет: и ffmpeg,
    и раздача живут ровно на время показа и гасятся вместе с ним, что бы ни случилось.

    Упаковка за показ перезапускается столько раз, сколько человек перемотал: манифест
    обещает приёмнику весь фильм, а :class:`Feed` пакует то место, которое он попросил.
    Раздача, приёмник и LOAD при этом одни на весь показ.

    ``follow`` - чем прогреву заняться, когда эта серия ляжет на диск целиком
    (:attr:`torrcast.usecases.warm.warmer.Warmer.follow`); у фильма его нет и быть не может.

    ``supply`` - источник показа (:class:`torrcast.ports.stream_source.StreamSource`): служба и наша
    раздача в ней. Спрашивают его только на краю показа, зато прежде, чем объявить показ
    погасшим, - иначе за аварию источника отвечает приёмник, который ни при чём.

    ``profile`` - пороги ПРИЁМНИКА (:mod:`torrcast.domain.profile`): вес куска, терпение, сторож
    нуджей, удержание запроса вместо 404. Умолчание осторожное - тот же Q70D, что и был.
    """
    out = _state.hls_dir(str(hls_root(config.hls_dir)))
    start = watch.entry.pos if watch else 0.0
    length = watch.entry.dur if watch else duration
    tls = config.transport == "https"
    video_mbit = max(0.0, watch.entry.vbps) if watch else 0.0
    video_mbit_estimated = watch.entry.vbps_estimated if watch else False
    session_tag = session_tag or phrase("playback.session_tag", id=journal().session_id())
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
    grid, whole = layout(
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
        video_mbit_estimated=video_mbit_estimated,
        codec=codec,
        depth=depth,
        voice=voice,
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
        # 🔴 TC-1002. С какого места пойдёт показ, решает не закладка, а лента: картинка
        # начинается только с опорного кадра, и в слоте закладки его чаще всего нет вовсе
        # (:func:`torrcast.usecases.feed_pack.feed_restart._begin`). Место приезжает оттуда
        # одним числом - и упаковка, и LOAD идут по нему, иначе приёмнику называют секунду,
        # которой в выложенном потоке не с чего начаться.
        start = feed.begin(start)
        # 🔴 TC-1010. Это же число - единственная правда о месте посадки для CLI, который
        # ждёт картинку из другого процесса: закладка после TC-1002 законно расходится с
        # ним, а спросить показ иначе, чем файлом на общем диске, CLI не может.
        _state.mark_landed(out, start)
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
            print(phrase("playback.raising_myself", tag=session_tag, why=why(exc)), flush=True)
        else:
            journal().mark("LOAD взят")
            # Свою строку «старт NN с» показ говорит не здесь, а по первому кадру
            # (``say_started`` ниже): взятый LOAD - это слово ``PLAYING``, а оно
            # раньше картинки, и число от него занижено.
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
            say_started=lambda: print(
                phrase(
                    "playback.now_playing_tagged",
                    tag=session_tag,
                    about=about,
                    secs=f"{clock.total:.0f}",
                ),
                flush=True,
            ),
        )
    finally:
        _close_show(watch, warmer, receiver, feed, server)

    return _report_end(receiver, session_tag, watch, supply, expected_end)
